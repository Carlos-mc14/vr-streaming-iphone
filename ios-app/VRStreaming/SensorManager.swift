//
//  SensorManager.swift
//  VRStreaming
//
//  Manages device sensors (gyroscope, accelerometer) using CoreMotion.
//  Provides orientation data for head tracking.
//

import Foundation
import CoreMotion
import Combine

/// Sensor data structure for transmission
struct SensorData: Codable {
    let timestamp: Double
    let orientation: Quaternion
    let acceleration: Vector3
    let gyroscope: Vector3
    
    struct Quaternion: Codable {
        let x: Double
        let y: Double
        let z: Double
        let w: Double
    }
    
    struct Vector3: Codable {
        let x: Double
        let y: Double
        let z: Double
    }
}

/// Manages device motion sensors
class SensorManager: ObservableObject {
    
    // MARK: - Singleton
    
    static let shared = SensorManager()
    
    // MARK: - Published Properties
    
    @Published var isAvailable: Bool = false
    @Published var isRunning: Bool = false
    @Published var sensorRate: Double = 0
    @Published var currentOrientation: CMAttitude?
    
    // MARK: - Callback
    
    /// Callback for sensor updates
    var onSensorUpdate: ((SensorData) -> Void)?
    
    // MARK: - Private Properties
    
    private let motionManager = CMMotionManager()
    private let operationQueue = OperationQueue()
    
    // Reference attitude for recentering
    private var referenceAttitude: CMAttitude?
    
    // Update rate
    private let updateInterval: TimeInterval = 1.0 / 60.0  // 60 Hz
    
    // Metrics
    private var sampleCount: Int = 0
    private var lastRateUpdate: Date = Date()
    
    // MARK: - Initialization
    
    private init() {
        operationQueue.name = "com.vrstreaming.sensors"
        operationQueue.maxConcurrentOperationCount = 1
        operationQueue.qualityOfService = .userInteractive
        
        checkAvailability()
    }
    
    // MARK: - Availability
    
    private func checkAvailability() {
        isAvailable = motionManager.isDeviceMotionAvailable
        
        if !isAvailable {
            print("[SensorManager] Device motion not available")
        } else {
            print("[SensorManager] Device motion available")
        }
    }
    
    /// Request motion permissions
    func requestPermissions() {
        // CoreMotion doesn't require explicit permission request
        // but we should check availability
        checkAvailability()
    }
    
    // MARK: - Start/Stop
    
    /// Start sensor updates
    func startUpdates() {
        guard isAvailable && !isRunning else { return }
        
        print("[SensorManager] Starting sensor updates at \(1.0/updateInterval) Hz")
        
        // Configure motion manager
        motionManager.deviceMotionUpdateInterval = updateInterval
        
        // Use reference frame that includes magnetometer for absolute orientation
        motionManager.startDeviceMotionUpdates(
            using: .xArbitraryZVertical,
            to: operationQueue
        ) { [weak self] motion, error in
            self?.handleMotionUpdate(motion: motion, error: error)
        }
        
        isRunning = true
    }
    
    /// Stop sensor updates
    func stopUpdates() {
        guard isRunning else { return }
        
        print("[SensorManager] Stopping sensor updates")
        
        motionManager.stopDeviceMotionUpdates()
        isRunning = false
        sensorRate = 0
    }
    
    // MARK: - Motion Updates
    
    private func handleMotionUpdate(motion: CMDeviceMotion?, error: Error?) {
        if let error = error {
            print("[SensorManager] Motion error: \(error)")
            return
        }
        
        guard let motion = motion else { return }
        
        // Set reference attitude on first update if not set
        if referenceAttitude == nil {
            referenceAttitude = motion.attitude.copy() as? CMAttitude
        }
        
        // Get attitude relative to reference
        let attitude = motion.attitude
        if let reference = referenceAttitude {
            attitude.multiply(byInverseOf: reference)
        }
        
        // Update current orientation
        DispatchQueue.main.async {
            self.currentOrientation = attitude
        }
        
        // Create sensor data
        let sensorData = SensorData(
            timestamp: Date().timeIntervalSince1970,
            orientation: SensorData.Quaternion(
                x: attitude.quaternion.x,
                y: attitude.quaternion.y,
                z: attitude.quaternion.z,
                w: attitude.quaternion.w
            ),
            acceleration: SensorData.Vector3(
                x: motion.userAcceleration.x,
                y: motion.userAcceleration.y,
                z: motion.userAcceleration.z
            ),
            gyroscope: SensorData.Vector3(
                x: motion.rotationRate.x,
                y: motion.rotationRate.y,
                z: motion.rotationRate.z
            )
        )
        
        // Update metrics
        updateSensorRate()
        
        // Call callback
        onSensorUpdate?(sensorData)
    }
    
    private func updateSensorRate() {
        sampleCount += 1
        
        let now = Date()
        if now.timeIntervalSince(lastRateUpdate) >= 1.0 {
            DispatchQueue.main.async {
                self.sensorRate = Double(self.sampleCount)
            }
            sampleCount = 0
            lastRateUpdate = now
        }
    }
    
    // MARK: - Recentering
    
    /// Recenter the reference orientation
    func recenter() {
        print("[SensorManager] Recentering")
        
        // Reset reference to current attitude
        if let currentMotion = motionManager.deviceMotion {
            referenceAttitude = currentMotion.attitude.copy() as? CMAttitude
        } else {
            referenceAttitude = nil
        }
    }
    
    // MARK: - Utilities
    
    /// Get current euler angles in degrees
    func getCurrentEulerAngles() -> (pitch: Double, yaw: Double, roll: Double)? {
        guard let attitude = currentOrientation else { return nil }
        
        return (
            pitch: attitude.pitch * 180.0 / .pi,
            yaw: attitude.yaw * 180.0 / .pi,
            roll: attitude.roll * 180.0 / .pi
        )
    }
    
    /// Check if device is in landscape orientation
    var isLandscape: Bool {
        guard let attitude = currentOrientation else { return false }
        return abs(attitude.roll) > .pi / 4
    }
}

// MARK: - CMAttitude Extension

extension CMAttitude {
    /// Create a copy of the attitude
    func copy() -> CMAttitude? {
        // CMAttitude doesn't have a public copy method, so we archive and unarchive
        guard let data = try? NSKeyedArchiver.archivedData(
            withRootObject: self,
            requiringSecureCoding: false
        ) else { return nil }
        
        return try? NSKeyedUnarchiver.unarchivedObject(ofClass: CMAttitude.self, from: data)
    }
}
