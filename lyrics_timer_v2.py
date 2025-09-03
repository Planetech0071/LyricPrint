# Enhanced LRC per-word timestamp generator
# Requirements: pip install pygame
import pygame
import time
import sys
import os

def read_lrc_file(lrc_path):
    """Read lyrics from LRC file and return words, lines, and section structure."""
    words = []
    sections = []  # Each section is a list of lines
    word_to_section = {}  # Maps word position to (section_index, line_index, position)
    current_section = []
    last_timestamp = 0
    
    with open(lrc_path, 'r', encoding='utf-8') as f:
        for line in f:
            # Skip metadata lines
            if any(line.startswith(tag) for tag in ['[ti:', '[ar:', '[al:', '[id:', '[length:']):
                continue
            
            # Parse timestamp and line
            if line.strip() and '[' in line:
                # Extract timestamp
                timestamp_str = line[line.find('[')+1:line.find(']')]
                if ':' in timestamp_str:
                    mins, secs = map(float, timestamp_str.split(':'))
                    current_timestamp = mins * 60 + secs
                    
                    # Start new section if significant time gap (more than 4 seconds)
                    if current_section and ((current_timestamp - last_timestamp > 4.0) or len(current_section) >= 10):
                        if current_section:
                            sections.append(current_section)
                            current_section = []
                    
                    last_timestamp = current_timestamp
                
                # Remove timestamps and get clean line
                clean_line = ''.join(part.split(']')[-1] for part in line.split('[')).strip()
                
                if clean_line:
                    line_words = clean_line.split()
                    word_positions = []
                    current_pos = 0
                    
                    for word in line_words:
                        word_positions.append((current_pos, len(word)))
                        current_pos += len(word) + 1  # +1 for space
                    
                    for i, word in enumerate(line_words):
                        word_to_section[len(words)] = (
                            len(sections),  # section index
                            len(current_section),  # line index in section
                            word_positions[i]  # (position, length) in line
                        )
                        words.append(word)
                    current_section.append(clean_line)
    
    # Add the last section if not empty
    if current_section:
        sections.append(current_section)
    
    return words, sections, word_to_section

def get_valid_file_path(prompt, check_exists=True):
    while True:
        file_path = input(prompt).strip('"').strip()
        if not check_exists or os.path.exists(file_path):
            return file_path
        print(f"Error: File '{file_path}' not found. Please try again.")

def main():
    print("=== Per-word LRC Timestamp Generator ===")
    
    # Get input files
    mp3_file = get_valid_file_path("Enter the path to the MP3 file: ")
    lrc_file = get_valid_file_path("Enter the path to the input LRC file: ")
    output_file = r"C:\Users\monfortel_asmilan\Downloads\LyricPrint\lyrics.lrc"

    try:
        # Get words and structure from LRC file
        words, sections, word_to_section = read_lrc_file(lrc_file)
        if not words:
            print("Error: No lyrics found in the LRC file")
            return

        # Init pygame mixer
        pygame.mixer.init()
        try:
            pygame.mixer.music.load(mp3_file)
        except pygame.error:
            print(f"Error: Could not load MP3 file: {mp3_file}")
            return

        def display_lyrics(current_word_index=-1):
            import os
            os.system('cls' if os.name == 'nt' else 'clear')
            print(f"Loaded: {mp3_file}")
            print(f"\nProgress: [{current_word_index + 1}/{len(words)}] words")
            print("-" * 50)
            
            if current_word_index == -1:
                # Show first section
                print("\n".join(sections[0]))
            else:
                # Find current section
                current_section_idx = word_to_section[current_word_index][0]
                current_section = sections[current_section_idx].copy()
                
                # Replace all processed words with dots in current section
                for i in range(current_word_index + 1):
                    section_idx, line_idx, (pos, length) = word_to_section[i]
                    if section_idx == current_section_idx:
                        line = current_section[line_idx]
                        dots = '.' * length
                        current_section[line_idx] = line[:pos] + dots + line[pos + length:]
                
                # Display current section
                print("\n".join(current_section))
                
                # Show next section preview if current section is complete
                next_word_idx = current_word_index + 1
                if next_word_idx < len(words):
                    next_section_idx = word_to_section[next_word_idx][0]
                    if next_section_idx > current_section_idx:
                        print("\nNext section:")
                        print("-" * 50)
                        print("\n".join(sections[next_section_idx]))
            
            print("-" * 50)
            if current_word_index >= 0 and current_word_index < len(words) - 1:
                print(f"\nNext word: '{words[current_word_index + 1]}'")

        print("\nInstructions:")
        print("1. Press Enter to start the song")
        print("2. Press Enter for each word as it's sung")
        print("3. Press Ctrl+C to stop at any time")
        print("4. When you complete a section, the next one will be shown\n")
        
        display_lyrics()
        input("Press Enter to begin...")

        pygame.mixer.music.play()
        start_time = time.time()

        lrc_lines = []
        for i, word in enumerate(words):
            if i > 0:
                input()  # Wait for Enter
            curr_time = time.time() - start_time
            mins = int(curr_time // 60)
            secs = int(curr_time % 60)
            hundredths = int((curr_time - int(curr_time)) * 100)
            timestamp = f"[{mins:02d}:{secs:02d}.{hundredths:02d}]"
            lrc_lines.append(f"{timestamp}{word}")
            
            display_lyrics(i)  # Update display after each word

        # Save to output LRC file
        with open(output_file, 'w', encoding='utf-8') as f:
            for line in lrc_lines:
                f.write(line + '\n')
        print(f"\nSaved per-word LRC to {output_file}")

    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        pygame.mixer.quit()

if __name__ == '__main__':
    main()
