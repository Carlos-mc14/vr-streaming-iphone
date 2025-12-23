//
//  ContentView.swift
//  VRStreaming
//
//  Main content view with stereoscopic display and connection UI.
//

import SwiftUI

/// Main content view
struct ContentView: View {
    
    @EnvironmentObject var streamingManager: StreamingManager
    @StateObject private var sensorManager = SensorManager.shared
    
    @State private var showSettings = false
    @State private var showConnectionSheet = true
    @State private var serverAddress = "192.168.1.100"
    @State private var serverPort = "8889"
    
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
            
            // Instructions
            VStack(spacing: 5) {
                Text("Make sure:")
                    .font(.caption)
                    .foregroundColor(.gray)
                
                Text("• PC app is running")
                    .font(.caption)
                    .foregroundColor(.gray)
                
                Text("• Both devices on same network (WiFi)")
                    .font(.caption)
                    .foregroundColor(.gray)
                
                Text("• Or connected via USB cable")
                    .font(.caption)
                    .foregroundColor(.gray)
            }
            .padding(.top, 20)
        }
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
                    LabeledContent("Status", value: streamingManager.connectionState.displayName)
                    LabeledContent("Server", value: streamingManager.serverAddress)
                    
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
