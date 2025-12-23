//
//  StreamingManager.swift
//  VRStreaming
//
//  Manages network connection to PC and video stream reception.
//

import Foundation
import Network
import Combine
import UIKit

/// Connection state enumeration
enum ConnectionState: String {
    case disconnected
    case connecting
    case connected
    case error
    
    var displayName: String {
        switch self {
        case .disconnected: return "Disconnected"
        case .connecting: return "Connecting..."
        case .connected: return "Connected"
        case .error: return "Error"
        }
    }
}

/// Protocol header structure
struct FrameHeader {
    static let magicVideo: UInt32 = 0x49565256  // "VRVI" in little endian
    static let magicSensor: UInt32 = 0x45535256 // "VRSE" in little endian
    static let magicCommand: UInt32 = 0x4D435256 // "VRCM" in little endian
    static let headerSize = 12
    
    let magic: UInt32
    let packetType: UInt32
    let dataLength: UInt32
}

/// Streaming manager - handles connection and video stream
class StreamingManager: ObservableObject {
    
    // MARK: - Singleton
    
    static let shared = StreamingManager()
    
    // MARK: - Published Properties
    
    @Published var connectionState: ConnectionState = .disconnected
    @Published var isConnected: Bool = false
    @Published var currentFPS: Double = 0
    @Published var latencyMs: Double = 0
    @Published var showError: Bool = false
    @Published var errorMessage: String = ""
    @Published var serverAddress: String = ""
    
    // MARK: - Frame Data
    
    /// Current video frame data (JPEG)
    private(set) var currentFrame: Data?
    
    /// Frame update callback
    var onFrameReceived: ((Data) -> Void)?
    
    // MARK: - Private Properties
    
    private var connection: NWConnection?
    private var connectionQueue = DispatchQueue(label: "com.vrstreaming.connection", qos: .userInteractive)
    private var receiveQueue = DispatchQueue(label: "com.vrstreaming.receive", qos: .userInteractive)
    private var sendQueue = DispatchQueue(label: "com.vrstreaming.send", qos: .userInteractive)
    
    // Buffer for receiving data
    private var receiveBuffer = Data()
    
    // Metrics
    private var frameCount: Int = 0
    private var lastFPSUpdate: Date = Date()
    private var lastFrameTime: Date = Date()
    
    // Sensor manager reference
    private var sensorManager: SensorManager?
    
    // MARK: - Initialization
    
    private init() {
        sensorManager = SensorManager.shared
        setupSensorCallback()
    }
    
    // MARK: - Connection Management
    
    /// Connect to server
    func connect(host: String, port: Int) {
        guard connectionState != .connecting else { return }
        
        serverAddress = "\(host):\(port)"
        connectionState = .connecting
        
        print("[StreamingManager] Connecting to \(host):\(port)")
        
        // Create network connection
        let endpoint = NWEndpoint.hostPort(
            host: NWEndpoint.Host(host),
            port: NWEndpoint.Port(integerLiteral: UInt16(port))
        )
        
        let parameters = NWParameters.tcp
        parameters.prohibitedInterfaceTypes = [.cellular]
        
        // Configure for low latency
        if let options = parameters.defaultProtocolStack.transportProtocol as? NWProtocolTCP.Options {
            options.noDelay = true
            options.connectionTimeout = 10
        }
        
        connection = NWConnection(to: endpoint, using: parameters)
        
        // Set up state handler
        connection?.stateUpdateHandler = { [weak self] state in
            DispatchQueue.main.async {
                self?.handleStateChange(state)
            }
        }
        
        // Start connection
        connection?.start(queue: connectionQueue)
    }
    
    /// Disconnect from server
    func disconnect() {
        print("[StreamingManager] Disconnecting")
        
        connection?.cancel()
        connection = nil
        
        receiveBuffer.removeAll()
        currentFrame = nil
        
        DispatchQueue.main.async {
            self.connectionState = .disconnected
            self.isConnected = false
            self.currentFPS = 0
            self.latencyMs = 0
        }
    }
    
    /// Pause streaming (when app backgrounded)
    func pause() {
        sensorManager?.stopUpdates()
    }
    
    /// Resume streaming
    func resume() {
        if isConnected {
            sensorManager?.startUpdates()
        }
    }
    
    // MARK: - State Handling
    
    private func handleStateChange(_ state: NWConnection.State) {
        switch state {
        case .ready:
            print("[StreamingManager] Connected")
            connectionState = .connected
            isConnected = true
            
            // Start receiving data
            startReceiving()
            
            // Start sending sensor data
            sensorManager?.startUpdates()
            
        case .failed(let error):
            print("[StreamingManager] Connection failed: \(error)")
            connectionState = .error
            isConnected = false
            errorMessage = "Connection failed: \(error.localizedDescription)"
            showError = true
            
        case .cancelled:
            print("[StreamingManager] Connection cancelled")
            connectionState = .disconnected
            isConnected = false
            
        case .preparing:
            connectionState = .connecting
            
        case .waiting(let error):
            print("[StreamingManager] Waiting: \(error)")
            connectionState = .connecting
            
        default:
            break
        }
    }
    
    // MARK: - Data Reception
    
    private func startReceiving() {
        receiveData()
    }
    
    private func receiveData() {
        connection?.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, context, isComplete, error in
            guard let self = self else { return }
            
            if let data = data, !data.isEmpty {
                self.receiveQueue.async {
                    self.processReceivedData(data)
                }
            }
            
            if let error = error {
                print("[StreamingManager] Receive error: \(error)")
                DispatchQueue.main.async {
                    self.disconnect()
                }
                return
            }
            
            if isComplete {
                print("[StreamingManager] Connection closed by server")
                DispatchQueue.main.async {
                    self.disconnect()
                }
                return
            }
            
            // Continue receiving
            self.receiveData()
        }
    }
    
    private func processReceivedData(_ data: Data) {
        receiveBuffer.append(data)
        
        // Process complete packets
        while receiveBuffer.count >= FrameHeader.headerSize {
            // Read header
            let magic = receiveBuffer.withUnsafeBytes { $0.load(as: UInt32.self) }
            
            // Check for valid magic number
            guard magic == FrameHeader.magicVideo ||
                  magic == FrameHeader.magicCommand else {
                // Invalid magic, try to resync
                if let index = findNextMagic() {
                    receiveBuffer.removeSubrange(0..<index)
                } else {
                    receiveBuffer.removeAll()
                }
                continue
            }
            
            // Parse header
            let packetType = receiveBuffer.withUnsafeBytes { 
                $0.load(fromByteOffset: 4, as: UInt32.self) 
            }
            let dataLength = receiveBuffer.withUnsafeBytes { 
                $0.load(fromByteOffset: 8, as: UInt32.self) 
            }
            
            let totalLength = FrameHeader.headerSize + Int(dataLength)
            
            // Check if we have complete packet
            guard receiveBuffer.count >= totalLength else {
                break  // Wait for more data
            }
            
            // Extract packet data
            let packetData = receiveBuffer.subdata(in: FrameHeader.headerSize..<totalLength)
            receiveBuffer.removeSubrange(0..<totalLength)
            
            // Process packet
            if magic == FrameHeader.magicVideo {
                processVideoFrame(packetData)
            } else if magic == FrameHeader.magicCommand {
                processCommand(packetData)
            }
        }
    }
    
    private func findNextMagic() -> Int? {
        let videoMagic = Data([0x56, 0x52, 0x56, 0x49])  // "VRVI"
        let cmdMagic = Data([0x56, 0x52, 0x43, 0x4D])    // "VRCM"
        
        for i in 1..<receiveBuffer.count {
            if receiveBuffer.count - i >= 4 {
                let slice = receiveBuffer.subdata(in: i..<i+4)
                if slice == videoMagic || slice == cmdMagic {
                    return i
                }
            }
        }
        return nil
    }
    
    private func processVideoFrame(_ data: Data) {
        // Update frame
        currentFrame = data
        
        // Calculate metrics
        let now = Date()
        frameCount += 1
        
        // Calculate latency (time since last frame)
        latencyMs = now.timeIntervalSince(lastFrameTime) * 1000
        lastFrameTime = now
        
        // Update FPS every second
        if now.timeIntervalSince(lastFPSUpdate) >= 1.0 {
            DispatchQueue.main.async {
                self.currentFPS = Double(self.frameCount)
            }
            frameCount = 0
            lastFPSUpdate = now
        }
        
        // Notify callback
        DispatchQueue.main.async {
            self.onFrameReceived?(data)
        }
    }
    
    private func processCommand(_ data: Data) {
        // Parse command JSON
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let commandType = json["type"] as? String else {
            return
        }
        
        print("[StreamingManager] Received command: \(commandType)")
        
        switch commandType {
        case "pong":
            // Server responded to ping
            break
        case "config":
            // Update configuration
            break
        default:
            break
        }
    }
    
    // MARK: - Data Sending
    
    /// Send sensor data to PC
    func sendSensorData(_ sensorData: SensorData) {
        guard isConnected, let connection = connection else { return }
        
        // Encode sensor data as JSON
        guard let jsonData = try? JSONEncoder().encode(sensorData) else {
            return
        }
        
        // Create packet with header
        var packet = Data()
        
        // Magic number (VRSE)
        var magic: UInt32 = FrameHeader.magicSensor
        packet.append(Data(bytes: &magic, count: 4))
        
        // Packet type (0 for sensor)
        var packetType: UInt32 = 0
        packet.append(Data(bytes: &packetType, count: 4))
        
        // Data length
        var length: UInt32 = UInt32(jsonData.count)
        packet.append(Data(bytes: &length, count: 4))
        
        // Data
        packet.append(jsonData)
        
        // Send
        connection.send(content: packet, completion: .contentProcessed { error in
            if let error = error {
                print("[StreamingManager] Send error: \(error)")
            }
        })
    }
    
    /// Send command to PC
    func sendCommand(_ command: [String: Any]) {
        guard isConnected, let connection = connection else { return }
        
        guard let jsonData = try? JSONSerialization.data(withJSONObject: command) else {
            return
        }
        
        // Create packet with header
        var packet = Data()
        
        // Magic number (VRCM)
        var magic: UInt32 = FrameHeader.magicCommand
        packet.append(Data(bytes: &magic, count: 4))
        
        // Packet type
        var packetType: UInt32 = 1
        packet.append(Data(bytes: &packetType, count: 4))
        
        // Data length
        var length: UInt32 = UInt32(jsonData.count)
        packet.append(Data(bytes: &length, count: 4))
        
        // Data
        packet.append(jsonData)
        
        // Send
        connection.send(content: packet, completion: .contentProcessed { _ in })
    }
    
    // MARK: - Sensor Callback
    
    private func setupSensorCallback() {
        sensorManager?.onSensorUpdate = { [weak self] sensorData in
            self?.sendSensorData(sensorData)
        }
    }
}
