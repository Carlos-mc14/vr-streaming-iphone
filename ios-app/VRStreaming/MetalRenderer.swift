//
//  MetalRenderer.swift
//  VRStreaming
//
//  High-performance Metal renderer for stereoscopic VR display.
//  Includes barrel distortion correction for VR lenses.
//

import Foundation
import Metal
import MetalKit
import simd

/// Metal renderer for VR display
class MetalRenderer {
    
    // MARK: - Metal Objects
    
    private let device: MTLDevice
    private let commandQueue: MTLCommandQueue
    private var pipelineState: MTLRenderPipelineState?
    private var samplerState: MTLSamplerState?
    
    // MARK: - Textures
    
    private var videoTexture: MTLTexture?
    private var textureLoader: MTKTextureLoader
    
    // MARK: - Geometry
    
    private var vertexBuffer: MTLBuffer?
    private var indexBuffer: MTLBuffer?
    private var uniformBuffer: MTLBuffer?
    
    // MARK: - Distortion Parameters
    
    private var distortionEnabled: Bool = true
    private var distortionK1: Float = 0.22
    private var distortionK2: Float = 0.24
    
    // MARK: - Uniforms
    
    struct Uniforms {
        var distortionEnabled: Int32
        var k1: Float
        var k2: Float
        var padding: Float
        var leftEyeCenter: SIMD2<Float>
        var rightEyeCenter: SIMD2<Float>
        var viewportSize: SIMD2<Float>
        var textureSize: SIMD2<Float>
    }
    
    // MARK: - Vertex Data
    
    struct Vertex {
        var position: SIMD4<Float>
        var texCoord: SIMD2<Float>
    }
    
    // MARK: - Initialization
    
    init?(device: MTLDevice, pixelFormat: MTLPixelFormat) {
        self.device = device
        
        guard let queue = device.makeCommandQueue() else {
            print("[MetalRenderer] Failed to create command queue")
            return nil
        }
        self.commandQueue = queue
        
        self.textureLoader = MTKTextureLoader(device: device)
        
        // Set up pipeline
        setupPipeline(pixelFormat: pixelFormat)
        setupGeometry()
        setupSampler()
    }
    
    // MARK: - Setup
    
    private func setupPipeline(pixelFormat: MTLPixelFormat) {
        // Create shader library from source
        let shaderSource = """
        #include <metal_stdlib>
        using namespace metal;
        
        struct VertexIn {
            float4 position [[attribute(0)]];
            float2 texCoord [[attribute(1)]];
        };
        
        struct VertexOut {
            float4 position [[position]];
            float2 texCoord;
        };
        
        struct Uniforms {
            int distortionEnabled;
            float k1;
            float k2;
            float padding;
            float2 leftEyeCenter;
            float2 rightEyeCenter;
            float2 viewportSize;
            float2 textureSize;
        };
        
        vertex VertexOut vertexShader(VertexIn in [[stage_in]]) {
            VertexOut out;
            out.position = in.position;
            out.texCoord = in.texCoord;
            return out;
        }
        
        // Apply barrel distortion
        float2 applyBarrelDistortion(float2 coord, float2 center, float k1, float k2) {
            float2 delta = coord - center;
            float r2 = dot(delta, delta);
            float r4 = r2 * r2;
            float factor = 1.0 + k1 * r2 + k2 * r4;
            return center + delta * factor;
        }
        
        fragment float4 fragmentShader(VertexOut in [[stage_in]],
                                       texture2d<float> texture [[texture(0)]],
                                       sampler texSampler [[sampler(0)]],
                                       constant Uniforms& uniforms [[buffer(0)]]) {
            float2 texCoord = in.texCoord;
            
            if (uniforms.distortionEnabled != 0) {
                // Determine which eye we're rendering
                float2 center;
                if (texCoord.x < 0.5) {
                    // Left eye
                    center = uniforms.leftEyeCenter;
                } else {
                    // Right eye
                    center = uniforms.rightEyeCenter;
                }
                
                // Apply barrel distortion
                texCoord = applyBarrelDistortion(texCoord, center, uniforms.k1, uniforms.k2);
            }
            
            // Clamp to valid range
            texCoord = clamp(texCoord, float2(0.0), float2(1.0));
            
            // Sample texture
            float4 color = texture.sample(texSampler, texCoord);
            
            // Add slight vignette effect for VR
            float2 pos = texCoord;
            if (pos.x > 0.5) {
                pos.x = pos.x - 0.5;
            }
            pos = pos * 2.0 - float2(0.5, 0.5);
            float vignette = 1.0 - dot(pos, pos) * 0.3;
            color.rgb *= vignette;
            
            return color;
        }
        """
        
        do {
            let library = try device.makeLibrary(source: shaderSource, options: nil)
            
            guard let vertexFunction = library.makeFunction(name: "vertexShader"),
                  let fragmentFunction = library.makeFunction(name: "fragmentShader") else {
                print("[MetalRenderer] Failed to create shader functions")
                return
            }
            
            let descriptor = MTLRenderPipelineDescriptor()
            descriptor.vertexFunction = vertexFunction
            descriptor.fragmentFunction = fragmentFunction
            descriptor.colorAttachments[0].pixelFormat = pixelFormat
            
            // Vertex descriptor
            let vertexDescriptor = MTLVertexDescriptor()
            vertexDescriptor.attributes[0].format = .float4
            vertexDescriptor.attributes[0].offset = 0
            vertexDescriptor.attributes[0].bufferIndex = 0
            
            vertexDescriptor.attributes[1].format = .float2
            vertexDescriptor.attributes[1].offset = MemoryLayout<SIMD4<Float>>.size
            vertexDescriptor.attributes[1].bufferIndex = 0
            
            vertexDescriptor.layouts[0].stride = MemoryLayout<Vertex>.size
            
            descriptor.vertexDescriptor = vertexDescriptor
            
            pipelineState = try device.makeRenderPipelineState(descriptor: descriptor)
            
            print("[MetalRenderer] Pipeline created successfully")
            
        } catch {
            print("[MetalRenderer] Failed to create pipeline: \(error)")
        }
    }
    
    private func setupGeometry() {
        // Full screen quad
        let vertices: [Vertex] = [
            Vertex(position: SIMD4<Float>(-1, -1, 0, 1), texCoord: SIMD2<Float>(0, 1)),
            Vertex(position: SIMD4<Float>( 1, -1, 0, 1), texCoord: SIMD2<Float>(1, 1)),
            Vertex(position: SIMD4<Float>( 1,  1, 0, 1), texCoord: SIMD2<Float>(1, 0)),
            Vertex(position: SIMD4<Float>(-1,  1, 0, 1), texCoord: SIMD2<Float>(0, 0))
        ]
        
        let indices: [UInt16] = [0, 1, 2, 0, 2, 3]
        
        vertexBuffer = device.makeBuffer(
            bytes: vertices,
            length: vertices.count * MemoryLayout<Vertex>.size,
            options: .storageModeShared
        )
        
        indexBuffer = device.makeBuffer(
            bytes: indices,
            length: indices.count * MemoryLayout<UInt16>.size,
            options: .storageModeShared
        )
        
        // Create uniform buffer
        uniformBuffer = device.makeBuffer(
            length: MemoryLayout<Uniforms>.size,
            options: .storageModeShared
        )
    }
    
    private func setupSampler() {
        let descriptor = MTLSamplerDescriptor()
        descriptor.minFilter = .linear
        descriptor.magFilter = .linear
        descriptor.mipFilter = .nearest
        descriptor.sAddressMode = .clampToEdge
        descriptor.tAddressMode = .clampToEdge
        
        samplerState = device.makeSamplerState(descriptor: descriptor)
    }
    
    // MARK: - Texture Update
    
    /// Update video texture with new JPEG data
    func updateTexture(with jpegData: Data) {
        do {
            // Decode JPEG and create texture
            let options: [MTKTextureLoader.Option: Any] = [
                .generateMipmaps: false,
                .SRGB: false
            ]
            
            videoTexture = try textureLoader.newTexture(data: jpegData, options: options)
            
        } catch {
            print("[MetalRenderer] Failed to create texture: \(error)")
        }
    }
    
    // MARK: - Rendering
    
    /// Render frame to drawable
    func render(
        to drawable: CAMetalDrawable,
        renderPassDescriptor: MTLRenderPassDescriptor,
        enableBarrelDistortion: Bool
    ) {
        guard let pipelineState = pipelineState,
              let vertexBuffer = vertexBuffer,
              let indexBuffer = indexBuffer,
              let uniformBuffer = uniformBuffer,
              let samplerState = samplerState,
              let texture = videoTexture else {
            return
        }
        
        // Update uniforms
        var uniforms = Uniforms(
            distortionEnabled: enableBarrelDistortion ? 1 : 0,
            k1: distortionK1,
            k2: distortionK2,
            padding: 0,
            leftEyeCenter: SIMD2<Float>(0.25, 0.5),
            rightEyeCenter: SIMD2<Float>(0.75, 0.5),
            viewportSize: SIMD2<Float>(Float(drawable.texture.width), Float(drawable.texture.height)),
            textureSize: SIMD2<Float>(Float(texture.width), Float(texture.height))
        )
        
        memcpy(uniformBuffer.contents(), &uniforms, MemoryLayout<Uniforms>.size)
        
        // Create command buffer
        guard let commandBuffer = commandQueue.makeCommandBuffer() else { return }
        
        // Create render encoder
        guard let encoder = commandBuffer.makeRenderCommandEncoder(descriptor: renderPassDescriptor) else { 
            return 
        }
        
        encoder.setRenderPipelineState(pipelineState)
        encoder.setVertexBuffer(vertexBuffer, offset: 0, index: 0)
        encoder.setFragmentTexture(texture, index: 0)
        encoder.setFragmentSamplerState(samplerState, index: 0)
        encoder.setFragmentBuffer(uniformBuffer, offset: 0, index: 0)
        
        // Draw
        encoder.drawIndexedPrimitives(
            type: .triangle,
            indexCount: 6,
            indexType: .uint16,
            indexBuffer: indexBuffer,
            indexBufferOffset: 0
        )
        
        encoder.endEncoding()
        
        // Present and commit
        commandBuffer.present(drawable)
        commandBuffer.commit()
    }
    
    // MARK: - Configuration
    
    /// Update view size
    func updateViewSize(_ size: CGSize) {
        // View size updated
    }
    
    /// Update drawable size
    func updateDrawableSize(_ size: CGSize) {
        // Drawable size updated
    }
    
    /// Set barrel distortion parameters
    func setDistortion(enabled: Bool, k1: Float = 0.22, k2: Float = 0.24) {
        distortionEnabled = enabled
        distortionK1 = k1
        distortionK2 = k2
    }
}
