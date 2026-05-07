#!/usr/bin/env python3
"""
Video Recorder - Captures screen and records to MP4 video
Supports multi-platform screen capture and video encoding
"""

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

import cv2
import mss
import numpy as np
from threading import Thread, Event

logger = logging.getLogger(__name__)


class ScreenRecorder:
    """
    Records screen to MP4 video file
    Uses MSS for fast screen capture and OpenCV for video encoding
    """
    
    def __init__(
        self,
        fps: int = 30,
        quality: int = 80,
        codec: str = 'mp4v',
        output_dir: str = './recordings'
    ):
        """
        Initialize screen recorder
        
        Args:
            fps: Frames per second (default 30)
            quality: Video quality 0-100 (default 80)
            codec: Video codec (default mp4v)
            output_dir: Output directory for recordings
        """
        self.fps = fps
        self.quality = quality
        self.codec = codec
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Recording state
        self.is_recording = False
        self.recording_thread = None
        self.stop_event = Event()
        
        # Video writer
        self.out = None
        self.recording_info = {}
    
    def start_recording(self, session_id: str) -> str:
        """
        Start recording screen
        
        Args:
            session_id: Unique session identifier
        
        Returns:
            Path to recording file
        """
        if self.is_recording:
            logger.warning("Recording already in progress")
            return None
        
        # Create filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"recording_{session_id}_{timestamp}.mp4"
        filepath = self.output_dir / filename
        
        self.recording_info = {
            'session_id': session_id,
            'filename': filename,
            'filepath': str(filepath),
            'start_time': datetime.now(),
            'frames_captured': 0,
            'status': 'recording'
        }
        
        self.is_recording = True
        self.stop_event.clear()
        
        # Start recording in separate thread
        self.recording_thread = Thread(
            target=self._record_screen,
            args=(str(filepath),),
            daemon=True
        )
        self.recording_thread.start()
        
        logger.info(f"Recording started: {filepath}")
        return str(filepath)
    
    def stop_recording(self) -> Dict:
        """
        Stop recording
        
        Returns:
            Recording info dictionary
        """
        if not self.is_recording:
            logger.warning("No recording in progress")
            return None
        
        self.is_recording = False
        self.stop_event.set()
        
        # Wait for thread to finish
        if self.recording_thread:
            self.recording_thread.join(timeout=5)
        
        # Close video writer
        if self.out:
            self.out.release()
            self.out = None
        
        # Update recording info
        self.recording_info['end_time'] = datetime.now()
        self.recording_info['status'] = 'completed'
        duration = (
            self.recording_info['end_time'] - self.recording_info['start_time']
        ).total_seconds()
        self.recording_info['duration_seconds'] = duration
        
        # Get file size
        try:
            file_size = Path(self.recording_info['filepath']).stat().st_size
            self.recording_info['file_size_bytes'] = file_size
            self.recording_info['file_size_mb'] = round(file_size / (1024 * 1024), 2)
        except Exception as e:
            logger.error(f"Error getting file size: {e}")
        
        logger.info(f"Recording stopped: {self.recording_info['filename']}")
        return self.recording_info
    
    def _record_screen(self, filepath: str) -> None:
        """
        Internal method to record screen
        
        Args:
            filepath: Output file path
        """
        try:
            # Initialize screen capture
            monitor = {'top': 0, 'left': 0, 'width': 1920, 'height': 1080}
            
            with mss.mss() as sct:
                # Get monitor info (use primary monitor if available)
                if sct.monitors:
                    monitor = sct.monitors[1]  # Primary monitor
            
            width = monitor['width']
            height = monitor['height']
            
            # Initialize video writer
            fourcc = cv2.VideoWriter_fourcc(*self.codec)
            self.out = cv2.VideoWriter(
                filepath,
                fourcc,
                self.fps,
                (width, height)
            )
            
            if not self.out.isOpened():
                logger.error(f"Failed to open video writer for {filepath}")
                return
            
            frame_count = 0
            
            # Capture frames
            with mss.mss() as sct:
                while self.is_recording and not self.stop_event.is_set():
                    try:
                        # Capture screenshot
                        screenshot = sct.grab(monitor)
                        
                        # Convert to numpy array
                        frame = np.array(screenshot)
                        
                        # Convert BGRA to BGR (OpenCV format)
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                        
                        # Resize if needed (for performance)
                        if frame.shape[:2] != (height, width):
                            frame = cv2.resize(frame, (width, height))
                        
                        # Apply quality compression if needed
                        if self.quality < 100:
                            # JPEG quality equivalent
                            quality = int(1 + (self.quality / 100) * 254)
                            _, frame = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
                            frame = cv2.imdecode(frame, cv2.IMREAD_COLOR)
                        
                        # Write frame
                        self.out.write(frame)
                        frame_count += 1
                        self.recording_info['frames_captured'] = frame_count
                        
                    except Exception as e:
                        logger.error(f"Error capturing frame: {e}")
                        continue
            
            logger.info(f"Recording completed: {frame_count} frames captured")
        
        except Exception as e:
            logger.error(f"Error in _record_screen: {e}")
        finally:
            if self.out:
                self.out.release()
    
    def get_recording_info(self) -> Dict:
        """
        Get current recording information
        
        Returns:
            Recording info dictionary
        """
        return self.recording_info
    
    def is_recording_active(self) -> bool:
        """
        Check if recording is active
        
        Returns:
            True if recording is active
        """
        return self.is_recording
    
    @staticmethod
    def get_recordings(output_dir: str = './recordings') -> list:
        """
        Get list of recorded files
        
        Args:
            output_dir: Directory containing recordings
        
        Returns:
            List of recording files
        """
        recordings_path = Path(output_dir)
        if not recordings_path.exists():
            return []
        
        recordings = []
        for file in recordings_path.glob('*.mp4'):
            stat = file.stat()
            recordings.append({
                'filename': file.name,
                'filepath': str(file),
                'size_mb': round(stat.st_size / (1024 * 1024), 2),
                'created_at': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                'modified_at': datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
        
        return recordings
    
    @staticmethod
    def delete_recording(filepath: str) -> bool:
        """
        Delete a recording file
        
        Args:
            filepath: Path to recording file
        
        Returns:
            True if deleted successfully
        """
        try:
            Path(filepath).unlink()
            logger.info(f"Recording deleted: {filepath}")
            return True
        except Exception as e:
            logger.error(f"Error deleting recording: {e}")
            return False
