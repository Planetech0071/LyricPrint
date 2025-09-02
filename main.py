import pygame
import time
import sys
import threading
import requests
import re
import json
import os
import librosa
from typing import List, Tuple, Optional, Dict
from mutagen.mp3 import MP3
from mutagen import File
from difflib import SequenceMatcher

class LyricsSyncPlayer:
    def __init__(self):
        pygame.mixer.init()
        self.is_playing = False
        self.start_time = None
        self.lyrics_cache = {}
        
    def get_song_bpm(self, mp3_path: str) -> float:
        """Get the BPM of a song and convert it to a suitable typing speed"""
        try:
            # Load the audio file with a specific duration to speed up analysis
            y, sr = librosa.load(mp3_path, duration=30, offset=30)
            
            # Use onset detection for more reliable BPM detection
            onset_env = librosa.onset.onset_strength(y=y, sr=sr)
            tempo = librosa.beat.tempo(onset_envelope=onset_env, sr=sr)
            
            # Get the tempo as a scalar value
            if hasattr(tempo, '__len__'):
                tempo = tempo[0]
            
            # Convert BPM to typing speed (seconds)
            # Scale factor of 8 gives good results for typical song tempos
            typing_speed = 60.0 / (float(tempo) * 8)
            
            # Clamp the typing speed between 0.01 and 0.1 seconds
            typing_speed = max(0.01, min(0.1, typing_speed)) -0.02
            
            print(f"🎵 Detected song BPM: {float(tempo):.1f}")
            print(f"⚡ Adjusted typing speed: {typing_speed:.3f} seconds per character")
            
            return typing_speed
        except Exception as e:
            print(f"⚠️ Could not detect BPM: {e}")
            print("Using default typing speed of 0.03 seconds")
            return 0.03  # Return default speed if detection fails
        
    def slow_print(self, text: str, speed: float = 0.05):
        """Print text character by character with delay"""
        for char in text:
            if not self.is_playing:  # Stop printing if music stops
                break
            sys.stdout.write(char)
            sys.stdout.flush()
            time.sleep(speed)
    
    def load_mp3(self, mp3_path: str):
        """Load MP3 file"""
        try:
            pygame.mixer.music.load(mp3_path)
            return True
        except pygame.error as e:
            print(f"Error loading MP3: {e}")
            return False
    
    def normalize_text(self, text: str) -> str:
        """Normalize text for comparison by removing punctuation and converting to lowercase"""
        normalized = re.sub(r'[^\w\s]', '', text.lower())
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized
    
    def parse_lrc_file(self, lrc_path: str) -> List[Tuple[float, str]]:
        """Parse LRC format lyrics file"""
        lyrics_with_time = []
        try:
            with open(lrc_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Skip metadata tags
                    if line.startswith('[') and any(tag in line.lower() for tag in ['ar:', 'al:', 'ti:', 'length:', 'id:']):
                        continue
                        
                    # Parse timestamp [mm:ss.xx]
                    if line.startswith('[') and ']' in line:
                        try:
                            timestamp_str = line[1:line.index(']')]
                            lyric_text = line[line.index(']') + 1:].strip()
                            
                            # Parse mm:ss.xx format
                            if ':' in timestamp_str:
                                time_parts = timestamp_str.split(':')
                                minutes = int(time_parts[0])
                                seconds = float(time_parts[1])
                                total_seconds = minutes * 60 + seconds
                                
                                if lyric_text:  # Only add lines with actual lyrics
                                    lyrics_with_time.append((total_seconds, lyric_text))
                        except (ValueError, IndexError):
                            continue
                            
        except Exception as e:
            print(f"Error reading LRC file: {e}")
            return []
        
        return sorted(lyrics_with_time, key=lambda x: x[0])
    
    def create_word_timing_map(self, timing_lrc: str) -> Dict[str, float]:
        """Create a mapping of normalized words to their timestamps"""
        timing_words = self.parse_lrc_file(timing_lrc)
        word_timing_map = {}
        
        # Create a sequential list to handle duplicate words
        timing_sequence = []
        
        for timestamp, word in timing_words:
            normalized_word = self.normalize_text(word)
            if normalized_word:
                timing_sequence.append((timestamp, normalized_word, word))
        
        return timing_sequence
    
    def create_word_level_lyrics(self, structure_lrc: str, timing_lrc: str) -> List[Tuple[float, str, bool]]:
        """Create word-level timed lyrics using structure lines and word timings"""
        
        structure_lines = self.parse_lrc_file(structure_lrc)
        
        timing_sequence = self.create_word_timing_map(timing_lrc)
        
        if not structure_lines or not timing_sequence:
            print("❌ Could not parse one or both LRC files")
            return []
        
        # Create word-level timed lyrics
        word_level_lyrics = []
        timing_index = 0
        
        for line_timestamp, line_text in structure_lines:
            if not line_text.strip():
                continue
            
            # Split line into words (preserve original capitalization/punctuation)
            line_words = line_text.split()
            
            # For each word in the line, find its timing
            for word_index, word in enumerate(line_words):
                normalized_word = self.normalize_text(word)
                found_timing = None
                
                # Search for this word starting from current timing_index
                search_start = max(0, timing_index - 2)  # Allow some backtrack
                search_end = min(len(timing_sequence), timing_index + 50)  # Look ahead
                
                for search_idx in range(search_start, search_end):
                    if search_idx < len(timing_sequence):
                        timing_time, timing_norm_word, timing_orig_word = timing_sequence[search_idx]
                        
                        # Use fuzzy matching for word comparison
                        similarity = SequenceMatcher(None, normalized_word, timing_norm_word).ratio()
                        if similarity > 0.8:  # 80% similarity threshold
                            found_timing = timing_time
                            timing_index = search_idx + 1
                            break
                
                # If no timing found, estimate based on previous word or line timestamp
                if found_timing is None:
                    if word_index == 0:
                        found_timing = line_timestamp
                    else:
                        # Estimate timing based on previous word + small gap
                        prev_timing = word_level_lyrics[-1][0] if word_level_lyrics else line_timestamp
                        found_timing = prev_timing + 0.3  # 300ms gap
                
                # Add word with timing and whether it's the last word in line
                is_line_end = (word_index == len(line_words) - 1)
                word_level_lyrics.append((found_timing, word, is_line_end))
        
        # Sort by timestamp
        word_level_lyrics.sort(key=lambda x: x[0])
        
        return word_level_lyrics
    
    def play_with_word_timing(self, mp3_path: str, structure_lrc: str, timing_lrc: str, print_speed: float = 0.03):
        """Play MP3 with word-level timing from combined LRC files"""
        
        print(f"\n🎵 Now Playing: {os.path.basename(mp3_path)} 🎵")
        print("=" * 60)
        
        # Create word-level lyrics
        word_level_lyrics = self.create_word_level_lyrics(structure_lrc, timing_lrc)
        
        if not word_level_lyrics:
            print("\n❌ Could not create word-level timing.")
            print("\n🎵 Playing music without lyrics...")
            self.play_music_only(mp3_path)
            return
                
        # Start playbook
        if not self.load_mp3(mp3_path):
            return
            
        pygame.mixer.music.play()
        self.is_playing = True
        self.start_time = time.time()
        
        word_index = 0
        current_line_words = []
        
        try:
            while pygame.mixer.music.get_busy() and self.is_playing:
                current_time = time.time() - self.start_time
                
                # Check if it's time for the next word
                while (word_index < len(word_level_lyrics) and 
                       current_time >= word_level_lyrics[word_index][0]):
                    
                    timestamp, word, is_line_end = word_level_lyrics[word_index]
                    
                    # Add word to current line
                    current_line_words.append(word)
                    
                    # Print the word
                    if len(current_line_words) == 1:
                        # First word of line - print with music note
                        print("♪ ", end="")
                    else:
                        # Subsequent words - print with space
                        print(" ", end="")
                    
                    # Print the word character by character
                    self.slow_print(word, print_speed)
                    sys.stdout.flush()
                    
                    # If this is the end of a line, move to next line
                    if is_line_end:
                        print()  # New line
                        current_line_words = []
                    
                    word_index += 1
                
                time.sleep(0.05)  # Small delay to prevent excessive CPU usage
                
        except KeyboardInterrupt:
            print("\n\nℹ️  Playback stopped by user.")
        finally:
            self.stop()
            
        print("\n🎵 Song finished!")
    
    def play_with_lrc_file(self, mp3_path: str, lrc_path: str, print_speed: float = 0.03):
        """Play MP3 with lyrics from single LRC file"""
        
        print(f"\n🎵 Now Playing: {os.path.basename(mp3_path)} 🎵")
        print("=" * 60)
        
        # Parse LRC file
        lyrics_with_timestamps = self.parse_lrc_file(lrc_path)
        
        if not lyrics_with_timestamps:
            print("\n❌ Could not parse lyrics from LRC file.")
            print("\n🎵 Playing music without lyrics...")
            self.play_music_only(mp3_path)
            return
        
        print("✅ Lyrics loaded from LRC file!")
        print("🎼 Starting synchronized playback...")
        print("-" * 60)
        
        # Start playback
        if not self.load_mp3(mp3_path):
            return
            
        pygame.mixer.music.play()
        self.is_playing = True
        self.start_time = time.time()
        
        lyric_index = 0
        
        try:
            while pygame.mixer.music.get_busy() and self.is_playing:
                current_time = time.time() - self.start_time
                
                # Check if it's time for the next lyric
                while (lyric_index < len(lyrics_with_timestamps) and 
                       current_time >= lyrics_with_timestamps[lyric_index][0]):
                    
                    _, lyric_line = lyrics_with_timestamps[lyric_index]
                    
                    if lyric_line.strip():  # Only print non-empty lines
                        print("♪ ", end="")
                        self.slow_print(lyric_line, print_speed)
                        print()  # Add newline after each complete line
                    
                    lyric_index += 1
                
                time.sleep(0.1)  # Small delay to prevent excessive CPU usage
                
        except KeyboardInterrupt:
            print("\n\nℹ️  Playback stopped by user.")
        finally:
            self.stop()
            
        print("\n🎵 Song finished!")
    
    def play_music_only(self, mp3_path: str):
        """Play MP3 without lyrics"""
        if not self.load_mp3(mp3_path):
            return
        
        pygame.mixer.music.play()
        self.is_playing = True
        
        try:
            while pygame.mixer.music.get_busy():
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\nℹ️  Playback stopped by user.")
        finally:
            self.stop()
    
    def stop(self):
        """Stop playback"""
        self.is_playing = False
        pygame.mixer.music.stop()
        pygame.mixer.quit()

def get_available_songs(music_dir: str) -> List[str]:
    """Get list of available songs from MUSIC directory"""
    songs = []
    if os.path.exists(music_dir):
        for item in os.listdir(music_dir):
            song_path = os.path.join(music_dir, item)
            if os.path.isdir(song_path):
                # Check if it has the required files
                mp3_file = os.path.join(song_path, "song.mp3")
                structure_file = os.path.join(song_path, "structure.lrc")
                lyrics_file = os.path.join(song_path, "lyrics.lrc")
                
                if all(os.path.exists(f) for f in [mp3_file, structure_file, lyrics_file]):
                    songs.append(item)
    return songs

def main():
    """Main function with simplified song selection interface"""
    print("🎵 WORD-LEVEL LRC LYRICS MP3 PLAYER 🎵")
    print("=" * 50)
    
    print("\n📋 Required packages:")
    print("   pip install pygame mutagen librosa")
    
    print("\n💡 Features:")
    print("   • Automatic BPM detection for optimal typing speed")
    print("   • Word-level synchronized lyrics")
    print("   • Press Ctrl+C to stop playback")
    
    print("\n" + "="*50)
    
    # Get current directory and music folder
    current_dir = os.path.dirname(os.path.abspath(__file__))
    music_dir = os.path.join(current_dir, "MUSIC")
    
    player = LyricsSyncPlayer()
    
    while True:
        try:
            # Get available songs
            available_songs = get_available_songs(music_dir)
            
            if not available_songs:
                print("❌ No songs found in MUSIC folder!")
                print("💡 Make sure each song folder contains: song.mp3, structure.lrc, lyrics.lrc")
                break
            
            print(f"\n🎵 Available Songs ({len(available_songs)}):")
            for i, song in enumerate(available_songs, 1):
                print(f"{i}. {song}")
            print(f"{len(available_songs) + 1}. Exit")
            
            choice = input(f"\nChoose a song (1-{len(available_songs) + 1}): ").strip()
            
            try:
                choice_num = int(choice)
                if choice_num == len(available_songs) + 1:
                    break
                elif 1 <= choice_num <= len(available_songs):
                    selected_song = available_songs[choice_num - 1]
                    
                    # Build file paths
                    song_folder = os.path.join(music_dir, selected_song)
                    mp3_file = os.path.join(song_folder, "song.mp3")
                    structure_lrc = os.path.join(song_folder, "structure.lrc")
                    timing_lrc = os.path.join(song_folder, "lyrics.lrc")
                    
                    # Auto-detect BPM for typing speed
                    print_speed = player.get_song_bpm(mp3_file)
                    
                    print(f"\n🚀 Starting {selected_song}...")
                    print("💡 Press Ctrl+C to stop at any time")
                    print("💡 Each word will appear character-by-character at its precise timing!")
                    
                    # Always use word-level timing mode
                    player.play_with_word_timing(mp3_file, structure_lrc, timing_lrc, print_speed)
                    
                else:
                    print("❌ Invalid choice. Please try again.")
                    continue
                    
            except ValueError:
                print("❌ Please enter a valid number.")
                continue
            
            # Ask if user wants to play another song
            again = input("\n🔄 Play another song? (y/n): ").strip().lower()
            if again not in ['y', 'yes']:
                break
                
        except KeyboardInterrupt:
            print("\n\n👋 Thanks for using the MP3 Lyrics Player!")
            break
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")
            continue
    
    print("🎵 Goodbye!")

if __name__ == "__main__":
    main()