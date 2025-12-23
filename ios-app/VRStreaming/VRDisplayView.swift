//
//  VRDisplayView.swift
//  VRStreaming
//
//  Stereoscopic VR display view using Metal for high-performance rendering.
//

import SwiftUI
import MetalKit

/// VR display view wrapper for SwiftUI
struct VRDisplayView: View {
    
    @EnvironmentObject var streamingManager: StreamingManager
    @EnvironmentObject var sensorManager: SensorManager
    
    var body: some View {
        GeometryReader { geometry in
            MetalVRView(
                streamingManager: streamingManager,
                size: geometry.size
            )
            .ignoresSafeArea()
        }
    }
}

/// Metal-based VR rendering view
struct MetalVRView: UIViewRepresentable {
    
    let streamingManager: StreamingManager
    let size: CGSize
    
    func makeUIView(context: Context) -> MTKView {
        let mtkView = MTKView()
        mtkView.device = MTLCreateSystemDefaultDevice()
        mtkView.delegate = context.coordinator
        mtkView.preferredFramesPerSecond = 60
        mtkView.isPaused = false
        mtkView.enableSetNeedsDisplay = false
        mtkView.colorPixelFormat = .bgra8Unorm
        mtkView.clearColor = MTLClearColor(red: 0, green: 0, blue: 0, alpha: 1)
        
        // Configure for low latency
        mtkView.presentsWithTransaction = false
        
        return mtkView
    }
    
    func updateUIView(_ uiView: MTKView, context: Context) {
        context.coordinator.updateSize(size)
    }
    
    func makeCoordinator() -> MetalVRCoordinator {
        MetalVRCoordinator(streamingManager: streamingManager, size: size)
    }
}

/// Coordinator for Metal rendering
class MetalVRCoordinator: NSObject, MTKViewDelegate {
    
    private let streamingManager: StreamingManager
    private var renderer: MetalRenderer?
    private var viewSize: CGSize
    
    init(streamingManager: StreamingManager, size: CGSize) {
        self.streamingManager = streamingManager
        self.viewSize = size
        super.init()
    }
    
    func updateSize(_ size: CGSize) {
        viewSize = size
        renderer?.updateViewSize(size)
    }
    
    func mtkView(_ view: MTKView, drawableSizeWillChange size: CGSize) {
        // Initialize renderer if needed
        if renderer == nil, let device = view.device {
            renderer = MetalRenderer(device: device, pixelFormat: view.colorPixelFormat)
        }
        
        renderer?.updateDrawableSize(size)
    }
    
    func draw(in view: MTKView) {
        guard let renderer = renderer,
              let drawable = view.currentDrawable,
              let descriptor = view.currentRenderPassDescriptor else {
            return
        }
        
        // Get current frame from streaming manager
        if let frameData = streamingManager.currentFrame {
            renderer.updateTexture(with: frameData)
        }
        
        // Render frame
        renderer.render(
            to: drawable,
            renderPassDescriptor: descriptor,
            enableBarrelDistortion: true
        )
    }
}

// MARK: - Preview

struct VRDisplayView_Previews: PreviewProvider {
    static var previews: some View {
        VRDisplayView()
            .environmentObject(StreamingManager.shared)
            .environmentObject(SensorManager.shared)
    }
}
