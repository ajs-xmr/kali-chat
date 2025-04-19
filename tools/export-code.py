import os
import glob

def export_python_files():
    # Create output directory if it doesn't exist
    output_dir = "python_exports"
    os.makedirs(output_dir, exist_ok=True)
    
    # Process each Python file
    for python_file in glob.glob('*.py'):
        # Create output filename
        output_file = os.path.join(output_dir, f"{os.path.splitext(python_file)[0]}.txt")
        
        # Read the Python file content
        with open(python_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Write to output file in requested format
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"{python_file}\n")
            f.write("```\n")
            f.write(content)
            f.write("\n```\n")
        
        print(f"Exported {python_file} to {output_file}")

if __name__ == "__main__":
    export_python_files()
    print("Export complete!")
