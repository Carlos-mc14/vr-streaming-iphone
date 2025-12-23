//
//  VRStreamingApp.swift
//  VRStreaming
//
//  Main application entry point for VR Streaming iOS client.
//  Receives video stream from PC and sends sensor data back.
//

import SwiftUI

/// Main application entry point
@main
struct VRStreamingApp: App {
    
    /// App delegate for handling lifecycle events
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    
    /// Shared streaming manager instance
    @StateObject private var streamingManager = StreamingManager.shared
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(streamingManager)
                .preferredColorScheme(.dark)
                .statusBar(hidden: true)
        }
    }
}

/// App delegate for handling application lifecycle
class AppDelegate: NSObject, UIApplicationDelegate {
    
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        // Keep screen on during VR use
        UIApplication.shared.isIdleTimerDisabled = true
        
        // Request sensor permissions early
        SensorManager.shared.requestPermissions()
        
        print("VRStreaming app launched")
        return true
    }
    
    func applicationWillTerminate(_ application: UIApplication) {
        // Clean up streaming connection
        StreamingManager.shared.disconnect()
        
        // Re-enable screen timeout
        UIApplication.shared.isIdleTimerDisabled = false
    }
    
    func applicationDidEnterBackground(_ application: UIApplication) {
        // Pause streaming when backgrounded
        StreamingManager.shared.pause()
    }
    
    func applicationWillEnterForeground(_ application: UIApplication) {
        // Resume streaming
        StreamingManager.shared.resume()
    }
}
