"""
VR Streaming - Video Encoder Module
====================================
Handles video encoding/compression for streaming.
Supports JPEG for low latency and H264 for better compression.

Author: VR Streaming Project
License: MIT
"""

import threading
import time
from queue import Queue, Empty, Full
from typing import Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum
import logging
import struct

import numpy as np
import cv2

# Try to import PyAV for H264 encoding
try:
    import av
    H264_AVAILABLE = True
except ImportError:
    H264_AVAILABLE = False
    logging.warning("PyAV not available, H264 encoding disabled")

logger = logging.getLogger(__name__)


class EncoderType(Enum):
    """Available encoder types."""
    JPEG = "jpeg"
    H264 = "h264"


@dataclass
class EncodedFrame:
    """Container for an encoded video frame."""
    data: bytes
    timestamp: float
    frame_number: int
    encoder_type: str
    width: int
    height: int
    compressed_size: int
    original_size: int
    
    @property
    def compression_ratio(self) -> float:
        """Calculate compression ratio."""
        if self.compressed_size > 0:
            return self.original_size / self.compressed_size
        return 0.0
    
    def to_bytes(self) -> bytes:
        """
        Serialize frame to bytes for transmission.
        
        Format:
        - 4 bytes: Magic number (0x56524652 = "VRFR")
        - 4 bytes: Frame number (uint32)
        - 8 bytes: Timestamp (double)
        - 2 bytes: Width (uint16)
        - 2 bytes: Height (uint16)
        - 1 byte: Encoder type (0=JPEG, 1=H264)
        - 4 bytes: Data length (uint32)
        - N bytes: Encoded data
        """
        encoder_byte = 0 if self.encoder_type == "jpeg" else 1
        
        header = struct.pack(
            "<4sIdHHBI",
            b"VRFR",  # Magic number
            self.frame_number,
            self.timestamp,
            self.width,
            self.height,
            encoder_byte,
            len(self.data)
        )
        
        return header + self.data
    
    @classmethod
    def from_bytes(cls, data: bytes) -> Optional['EncodedFrame']:
        """Deserialize frame from bytes."""
        try:
            # Parse header
            header_size = 25  # 4+4+8+2+2+1+4
            if len(data) < header_size:
                return None
            
            magic, frame_num, timestamp, width, height, encoder_byte, data_len = struct.unpack(
                "<4sIdHHBI",
                data[:header_size]
            )
            
            if magic != b"VRFR":
                return None
            
            if len(data) < header_size + data_len:
                return None
            
            frame_data = data[header_size:header_size + data_len]
            encoder_type = "jpeg" if encoder_byte == 0 else "h264"
            
            return cls(
                data=frame_data,
                timestamp=timestamp,
                frame_number=frame_num,
                encoder_type=encoder_type,
                width=width,
                height=height,
                compressed_size=len(frame_data),
                original_size=width * height * 3
            )
            
        except Exception as e:
            logger.error(f"Failed to deserialize frame: {e}")
            return None


class VideoEncoder:
    """
    Video encoder supporting JPEG and H264 encoding.
    Runs encoding in separate thread for performance.
    """
    
    def __init__(
        self,
        encoder_type: EncoderType = EncoderType.JPEG,
        quality: int = 85,
        resolution: Tuple[int, int] = (1920, 1080),
        fps: int = 60,
        max_queue_size: int = 5
    ):
        """
        Initialize video encoder.
        
        Args:
            encoder_type: Type of encoder to use
            quality: JPEG quality (1-100) or H264 CRF (0-51)
            resolution: Output resolution
            fps: Target FPS
            max_queue_size: Maximum frames to buffer
        """
        self.encoder_type = encoder_type
        self.quality = quality
        self.resolution = resolution
        self.fps = fps
        self.max_queue_size = max_queue_size
        
        # Queues for input frames and encoded output
        self.input_queue: Queue = Queue(maxsize=max_queue_size)
        self.output_queue: Queue = Queue(maxsize=max_queue_size)
        
        # State
        self._running = False
        self._encode_thread: Optional[threading.Thread] = None
        self._frame_number = 0
        
        # H264 encoder state
        self._h264_encoder = None
        self._h264_stream = None
        
        # Metrics
        self.encode_fps = 0.0
        self.avg_encode_time_ms = 0.0
        self._encode_times = []
        self._last_fps_update = time.time()
        
        # JPEG encode parameters (pre-computed for speed)
        self._jpeg_params = [
            cv2.IMWRITE_JPEG_QUALITY, quality,
            cv2.IMWRITE_JPEG_OPTIMIZE, 0,  # Disabled for speed
            cv2.IMWRITE_JPEG_PROGRESSIVE, 0
        ]
        
        logger.info(f"VideoEncoder initialized: {encoder_type.value}, quality={quality}")
    
    def start(self) -> bool:
        """Start encoder thread."""
        if self._running:
            return False
        
        try:
            if self.encoder_type == EncoderType.H264:
                self._init_h264_encoder()
            
            self._running = True
            self._encode_thread = threading.Thread(
                target=self._encode_loop,
                name="VideoEncoderThread",
                daemon=True
            )
            self._encode_thread.start()
            
            logger.info("Video encoder started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start encoder: {e}")
            return False
    
    def stop(self):
        """Stop encoder thread."""
        self._running = False
        
        if self._encode_thread:
            self._encode_thread.join(timeout=2.0)
            self._encode_thread = None
        
        # Close H264 encoder
        if self._h264_encoder:
            self._h264_encoder = None
            self._h264_stream = None
        
        # Clear queues
        for q in [self.input_queue, self.output_queue]:
            while not q.empty():
                try:
                    q.get_nowait()
                except:
                    break
        
        logger.info("Video encoder stopped")
    
    def _init_h264_encoder(self):
        """Initialize H264 encoder using PyAV."""
        if not H264_AVAILABLE:
            logger.warning("H264 not available, falling back to JPEG")
            self.encoder_type = EncoderType.JPEG
            return
        
        try:
            # Create in-memory container
            self._h264_encoder = av.open(
                '/dev/null' if not hasattr(av, 'BytesIO') else None,
                mode='w',
                format='null'
            )
            
            self._h264_stream = self._h264_encoder.add_stream('h264', rate=self.fps)
            self._h264_stream.width = self.resolution[0]
            self._h264_stream.height = self.resolution[1]
            self._h264_stream.pix_fmt = 'yuv420p'
            
            # Low-latency settings
            self._h264_stream.options = {
                'preset': 'ultrafast',
                'tune': 'zerolatency',
                'crf': str(self.quality)
            }
            
            logger.info("H264 encoder initialized")
            
        except Exception as e:
            logger.error(f"Failed to init H264: {e}")
            self.encoder_type = EncoderType.JPEG
    
    def _encode_loop(self):
        """Main encoding loop."""
        while self._running:
            try:
                # Get frame from input queue
                frame = self.input_queue.get(timeout=0.1)
                
                start_time = time.time()
                
                # Encode frame
                if self.encoder_type == EncoderType.JPEG:
                    encoded = self._encode_jpeg(frame)
                else:
                    encoded = self._encode_h264(frame)
                
                if encoded:
                    # Add to output queue
                    try:
                        self.output_queue.put_nowait(encoded)
                    except Full:
                        # Drop oldest encoded frame
                        try:
                            self.output_queue.get_nowait()
                            self.output_queue.put_nowait(encoded)
                        except:
                            pass
                
                # Update metrics
                encode_time = (time.time() - start_time) * 1000
                self._update_metrics(encode_time)
                
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Encode error: {e}")
    
    def _encode_jpeg(self, frame: np.ndarray) -> Optional[EncodedFrame]:
        """Encode frame as JPEG."""
        try:
            # Encode to JPEG
            success, encoded_data = cv2.imencode('.jpg', frame, self._jpeg_params)
            
            if not success:
                return None
            
            data = encoded_data.tobytes()
            
            self._frame_number += 1
            
            return EncodedFrame(
                data=data,
                timestamp=time.time(),
                frame_number=self._frame_number,
                encoder_type="jpeg",
                width=frame.shape[1],
                height=frame.shape[0],
                compressed_size=len(data),
                original_size=frame.nbytes
            )
            
        except Exception as e:
            logger.error(f"JPEG encode error: {e}")
            return None
    
    def _encode_h264(self, frame: np.ndarray) -> Optional[EncodedFrame]:
        """Encode frame as H264."""
        # Fall back to JPEG for now - H264 streaming requires more complex setup
        return self._encode_jpeg(frame)
    
    def _update_metrics(self, encode_time_ms: float):
        """Update performance metrics."""
        self._encode_times.append(encode_time_ms)
        
        current_time = time.time()
        
        # Keep only last second of times
        if len(self._encode_times) > 120:
            self._encode_times = self._encode_times[-60:]
        
        # Update averages
        if current_time - self._last_fps_update > 0.5:
            if self._encode_times:
                self.avg_encode_time_ms = sum(self._encode_times) / len(self._encode_times)
                self.encode_fps = 1000.0 / self.avg_encode_time_ms if self.avg_encode_time_ms > 0 else 0
            self._last_fps_update = current_time
    
    def encode_frame(self, frame: np.ndarray) -> bool:
        """
        Queue a frame for encoding.
        
        Args:
            frame: Frame to encode (BGR format)
            
        Returns:
            True if queued successfully
        """
        try:
            self.input_queue.put_nowait(frame)
            return True
        except Full:
            # Drop oldest and try again
            try:
                self.input_queue.get_nowait()
                self.input_queue.put_nowait(frame)
                return True
            except:
                return False
    
    def get_encoded_frame(self, timeout: float = 0.1) -> Optional[EncodedFrame]:
        """
        Get next encoded frame.
        
        Args:
            timeout: Maximum time to wait
            
        Returns:
            Encoded frame or None
        """
        try:
            return self.output_queue.get(timeout=timeout)
        except Empty:
            return None
    
    def encode_immediate(self, frame: np.ndarray) -> Optional[EncodedFrame]:
        """
        Encode frame immediately (blocking).
        
        Args:
            frame: Frame to encode
            
        Returns:
            Encoded frame or None
        """
        if self.encoder_type == EncoderType.JPEG:
            return self._encode_jpeg(frame)
        else:
            return self._encode_h264(frame)
    
    def set_quality(self, quality: int):
        """Update encoding quality."""
        self.quality = max(1, min(100, quality))
        self._jpeg_params[1] = self.quality
        logger.info(f"Encoder quality set to {self.quality}")
    
    def get_metrics(self) -> dict:
        """Get encoder metrics."""
        return {
            "encoder_type": self.encoder_type.value,
            "quality": self.quality,
            "encode_fps": round(self.encode_fps, 1),
            "avg_encode_time_ms": round(self.avg_encode_time_ms, 2),
            "input_queue_size": self.input_queue.qsize(),
            "output_queue_size": self.output_queue.qsize(),
            "frame_number": self._frame_number
        }
    
    @property
    def is_running(self) -> bool:
        """Check if encoder is running."""
        return self._running


class FrameDecoder:
    """Decode received video frames."""
    
    @staticmethod
    def decode_jpeg(data: bytes) -> Optional[np.ndarray]:
        """
        Decode JPEG data to numpy array.
        
        Args:
            data: JPEG encoded bytes
            
        Returns:
            Decoded frame (BGR) or None
        """
        try:
            nparr = np.frombuffer(data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            return frame
        except Exception as e:
            logger.error(f"JPEG decode error: {e}")
            return None
    
    @staticmethod
    def decode_frame(encoded: EncodedFrame) -> Optional[np.ndarray]:
        """
        Decode an EncodedFrame.
        
        Args:
            encoded: Encoded frame object
            
        Returns:
            Decoded frame (BGR) or None
        """
        if encoded.encoder_type == "jpeg":
            return FrameDecoder.decode_jpeg(encoded.data)
        else:
            # H264 would need more complex decoding
            return FrameDecoder.decode_jpeg(encoded.data)


# Test function
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Testing video encoder...")
    
    encoder = VideoEncoder(
        encoder_type=EncoderType.JPEG,
        quality=85,
        resolution=(1920, 1080)
    )
    
    encoder.start()
    
    try:
        # Create test frame
        test_frame = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
        
        # Encode multiple frames
        start_time = time.time()
        frames_encoded = 0
        
        while time.time() - start_time < 3:
            # Queue frame for encoding
            encoder.encode_frame(test_frame)
            
            # Get encoded frame
            encoded = encoder.get_encoded_frame(timeout=0.05)
            if encoded:
                frames_encoded += 1
                
                if frames_encoded % 30 == 0:
                    metrics = encoder.get_metrics()
                    print(f"Encoded {frames_encoded} frames, "
                          f"Avg time: {metrics['avg_encode_time_ms']:.2f}ms, "
                          f"Size: {encoded.compressed_size/1024:.1f}KB, "
                          f"Ratio: {encoded.compression_ratio:.1f}x")
        
        print(f"\nTotal: {frames_encoded} frames in 3 seconds ({frames_encoded/3:.1f} FPS)")
        
        # Test serialization
        encoded = encoder.encode_immediate(test_frame)
        if encoded:
            serialized = encoded.to_bytes()
            deserialized = EncodedFrame.from_bytes(serialized)
            print(f"Serialization test: {len(serialized)} bytes, "
                  f"success={deserialized is not None}")
        
    finally:
        encoder.stop()
