//
//  ContentView.swift
//  VRStreaming
//
//  Main content view with stereoscopic display and connection UI.
//

import SwiftUI
import Darwin

/// Main content view
struct ContentView: View {
    
    @EnvironmentObject var streamingManager: StreamingManager
    @StateObject private var sensorManager = SensorManager.shared
    
    @State private var showSettings = false
    @State private var showConnectionSheet = true
    @State private var serverAddress = "127.0.0.1"  // Default to localhost for USB
    @State private var serverPort = "8889"
    @State private var connectionMode = "usb"  // "usb" or "wifi"
    
    var body: some View {
        ZStack {
            // Background
            Color.black.ignoresSafeArea()
            
            // Main content based on connection state
            if streamingManager.isConnected {
                // VR View when connected
                VRDisplayView()
                    .environmentObject(streamingManager)
                    .environmentObject(sensorManager)
            } else {
                // Connection UI when disconnected
                ConnectionView(
                    serverAddress: $serverAddress,
                    serverPort: $serverPort,
                    onConnect: connect
                )
            }
            
            // Overlay controls
            VStack {
                // Top bar with status
                HStack {
                    // Connection status indicator
                    HStack(spacing: 6) {
                        Circle()
                            .fill(statusColor)
                            .frame(width: 10, height: 10)
                        
                        Text(streamingManager.connectionState.displayName)
                            .font(.caption)
                            .foregroundColor(.white)
                    }
                    .padding(8)
                    .background(Color.black.opacity(0.5))
                    .cornerRadius(8)
                    
                    Spacer()
                    
                    // Settings button
                    if streamingManager.isConnected {
                        Button(action: { showSettings.toggle() }) {
                            Image(systemName: "gearshape.fill")
                                .foregroundColor(.white)
                                .padding(10)
                                .background(Color.black.opacity(0.5))
                                .cornerRadius(8)
                        }
                    }
                }
                .padding()
                
                Spacer()
                
                // Bottom bar with metrics
                if streamingManager.isConnected {
                    MetricsBar()
                        .environmentObject(streamingManager)
                        .environmentObject(sensorManager)
                }
            }
        }
        .sheet(isPresented: $showSettings) {
            SettingsView()
                .environmentObject(streamingManager)
                .environmentObject(sensorManager)
        }
        .alert("Connection Error", isPresented: $streamingManager.showError) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(streamingManager.errorMessage)
        }
    }
    
    /// Status indicator color based on connection state
    private var statusColor: Color {
        switch streamingManager.connectionState {
        case .connected:
            return .green
        case .connecting:
            return .yellow
        case .disconnected:
            return .gray
        case .error:
            return .red
        }
    }
    
    /// Connect to server
    private func connect() {
        guard let port = Int(serverPort) else {
            streamingManager.errorMessage = "Invalid port number"
            streamingManager.showError = true
            return
        }
        
        showConnectionSheet = false
        streamingManager.connect(host: serverAddress, port: port)
    }
}

/// Connection view shown when disconnected
struct ConnectionView: View {
    
    @Binding var serverAddress: String
    @Binding var serverPort: String
    let onConnect: () -> Void
    
    @EnvironmentObject var streamingManager: StreamingManager
    
    var body: some View {
        VStack(spacing: 30) {
            // Logo/Title
            VStack(spacing: 10) {
                Image(systemName: "visionpro")
                    .font(.system(size: 60))
                    .foregroundColor(.blue)
                
                Text("VR Streaming")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                    .foregroundColor(.white)
                
                Text("Connect to your PC")
                    .font(.subheadline)
                    .foregroundColor(.gray)
            }
            
            // Connection form
            VStack(spacing: 15) {
                // Server address
                VStack(alignment: .leading, spacing: 5) {
                    Text("Server IP Address")
                        .font(.caption)
                        .foregroundColor(.gray)
                    
                    TextField("192.168.1.100", text: $serverAddress)
                        .textFieldStyle(RoundedTextFieldStyle())
                        .keyboardType(.decimalPad)
                        .autocapitalization(.none)
                }
                
                // Port
                VStack(alignment: .leading, spacing: 5) {
                    Text("Port")
                        .font(.caption)
                        .foregroundColor(.gray)
                    
                    TextField("8889", text: $serverPort)
                        .textFieldStyle(RoundedTextFieldStyle())
                        .keyboardType(.numberPad)
                }
            }
            .padding(.horizontal, 40)
            
            // Connect button
            Button(action: onConnect) {
                HStack {
                    if streamingManager.connectionState == .connecting {
                        ProgressView()
                            .progressViewStyle(CircularProgressViewStyle(tint: .white))
                            .padding(.trailing, 5)
                    }
                    
                    Text(streamingManager.connectionState == .connecting ? "Connecting..." : "Connect")
                        .fontWeight(.semibold)
                }
                .frame(maxWidth: .infinity)
                .padding()
                .background(Color.blue)
                .foregroundColor(.white)
                .cornerRadius(12)
            }
            .disabled(streamingManager.connectionState == .connecting)
            .padding(.horizontal, 40)
            
            // Connection Mode Selector
            VStack(spacing: 10) {
                Text("Connection Mode")
                    .font(.caption)
                    .foregroundColor(.gray)
                
                HStack(spacing: 20) {
                    // USB Mode Button
                    Button(action: {
                        connectionMode = "usb"
                        serverAddress = "127.0.0.1"
                    }) {
                        VStack {
                            Image(systemName: "cable.connector")
                                .font(.title2)
                            Text("USB")
                                .font(.caption)
                        }
                        .frame(width: 80, height: 60)
                        .background(connectionMode == "usb" ? Color.blue : Color.gray.opacity(0.3))
                        .foregroundColor(.white)
                        .cornerRadius(10)
                    }
                    
                    // WiFi Mode Button
                    Button(action: {
                        connectionMode = "wifi"
                        serverAddress = getWiFiAddress()
                    }) {
                        VStack {
                            Image(systemName: "wifi")
                                .font(.title2)
                            Text("WiFi")
                                .font(.caption)
                        }
                        .frame(width: 80, height: 60)
                        .background(connectionMode == "wifi" ? Color.blue : Color.gray.opacity(0.3))
                        .foregroundColor(.white)
                        .cornerRadius(10)
                    }
                }
            }
            .padding(.horizontal, 40)
            
            // Instructions
            VStack(spacing: 5) {
                Text("Instructions:")
                    .font(.caption)
                    .fontWeight(.semibold)
                    .foregroundColor(.white)
                
                if connectionMode == "usb" {
                    Text("1. Connect iPhone to PC via USB-C cable")
                        .font(.caption)
                        .foregroundColor(.gray)
                    Text("2. PC app is running and streaming")
                        .font(.caption)
                        .foregroundColor(.gray)
                    Text("3. Keep address as 127.0.0.1")
                        .font(.caption)
                        .foregroundColor(.gray)
                } else {
                    Text("1. Both devices on same WiFi network")
                        .font(.caption)
                        .foregroundColor(.gray)
                    Text("2. Enter PC's IP address shown in app")
                        .font(.caption)
                        .foregroundColor(.gray)
                    Text("3. PC app is running and streaming")
                        .font(.caption)
                        .foregroundColor(.gray)
                }
            }
            .padding(.top, 20)
        }
    }
    
    /// Get device's WiFi IP address for display
    private func getWiFiAddress() -> String {
        var address = "192.168.1.100"
        var ifaddr: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&ifaddr) == 0 else { return address }
        defer { freeifaddrs(ifaddr) }
        
        var ptr = ifaddr
        while ptr != nil {
            defer { ptr = ptr?.pointee.ifa_next }
            let interface = ptr?.pointee
            let addrFamily = interface?.ifa_addr.pointee.sa_family
            
            if addrFamily == UInt8(AF_INET) {
                let name = String(cString: (interface?.ifa_name)!)
                if name == "en0" {  // WiFi interface
                    var hostname = [CChar](repeating: 0, count: Int(NI_MAXHOST))
                    getnameinfo(interface?.ifa_addr, socklen_t((interface?.ifa_addr.pointee.sa_len)!),
                               &hostname, socklen_t(hostname.count), nil, socklen_t(0), NI_NUMERICHOST)
                    address = String(cString: hostname)
                }
            }
        }
        return address
    }
}

/// Custom text field style
struct RoundedTextFieldStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
            .padding(12)
            .background(Color(UIColor.systemGray6))
            .cornerRadius(10)
            .foregroundColor(.white)
    }
}

/// Metrics bar showing FPS, latency, etc.
struct MetricsBar: View {
    
    @EnvironmentObject var streamingManager: StreamingManager
    @EnvironmentObject var sensorManager: SensorManager
    
    var body: some View {
        HStack(spacing: 20) {
            MetricItem(label: "FPS", value: String(format: "%.0f", streamingManager.currentFPS))
            MetricItem(label: "Latency", value: String(format: "%.0fms", streamingManager.latencyMs))
            MetricItem(label: "Sensors", value: String(format: "%.0f Hz", sensorManager.sensorRate))
        }
        .padding(10)
        .background(Color.black.opacity(0.6))
        .cornerRadius(10)
        .padding(.bottom, 20)
    }
}

/// Single metric item
struct MetricItem: View {
    let label: String
    let value: String
    
    var body: some View {
        VStack(spacing: 2) {
            Text(value)
                .font(.system(.body, design: .monospaced))
                .fontWeight(.bold)
                .foregroundColor(.white)
            
            Text(label)
                .font(.caption2)
                .foregroundColor(.gray)
        }
    }
}

/// Settings view
struct SettingsView: View {
    
    @EnvironmentObject var streamingManager: StreamingManager
    @EnvironmentObject var sensorManager: SensorManager
    @Environment(\.dismiss) var dismiss
    
    @State private var sensitivity: Double = 1.0
    @State private var barrelDistortion: Bool = true
    
    var body: some View {
        NavigationView {
            Form {
                // Sensor settings
                Section("Sensor Settings") {
                    VStack(alignment: .leading) {
                        Text("Sensitivity: \(String(format: "%.1f", sensitivity))")
                        Slider(value: $sensitivity, in: 0.5...3.0, step: 0.1)
                    }
                    
                    Toggle("Use Gyroscope", isOn: .constant(true))
                    Toggle("Use Accelerometer", isOn: .constant(true))
                }
                
                // Display settings
                Section("Display Settings") {
                    Toggle("Barrel Distortion", isOn: $barrelDistortion)
                    
                    VStack(alignment: .leading) {
                        Text("IPD (mm): 63")
                        Slider(value: .constant(63), in: 55...75, step: 1)
                    }
                }
                
                // Connection info
                Section("Connection") {
                    HStack {
                        Text("Status")
                        Spacer()
                        Text(streamingManager.connectionState.displayName)
                            .foregroundColor(.secondary)
                    }
                    HStack {
                        Text("Server")
                        Spacer()
                        Text(streamingManager.serverAddress)
                            .foregroundColor(.secondary)
                    }
                    
                    Button("Disconnect") {
                        streamingManager.disconnect()
                        dismiss()
                    }
                    .foregroundColor(.red)
                }
                
                // Actions
                Section("Actions") {
                    Button("Recenter View") {
                        sensorManager.recenter()
                    }
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
        }
    }
}

// MARK: - Preview

struct ContentView_Previews: PreviewProvider {
    static var previews: some View {
        ContentView()
            .environmentObject(StreamingManager.shared)
    }
}
