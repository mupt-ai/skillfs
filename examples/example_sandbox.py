#!/usr/bin/env python3
"""Example script demonstrating how to create and use a sandbox with skillfs.

This script shows various ways to interact with E2B sandboxes including:
- Basic code execution
- File operations (upload/download)
- Using context managers for automatic cleanup
- Custom configuration
"""

from pathlib import Path
from skillfs.sandboxes import E2BSandbox, SandboxConfig

def example_bash_usage():
    """Example of using bash commands in the sandbox."""
    print("=== Example 1: Shell Command Usage ===")
    import time
    time_start = time.time()
    with E2BSandbox.create() as sandbox:
        # Use run_command for shell commands
        result = sandbox.run_command("git clone https://github.com/mupt-ai/dari-python.git")
        print(f"Time taken to create directory and file: {time.time() - time_start} seconds")
        print(f"Exit code: {result.exit_code}")

        time_start = time.time()
        result = sandbox.run_command("ls -la dari-python")
        print(f"Time taken to list files: {time.time() - time_start} seconds")
        print(f"Output:\n{result.logs}")

        # Test with custom working directory
        result = sandbox.run_command("pwd", cwd="/tmp")
        print(f"Current directory: {result.logs.strip()}")
    time_end = time.time()
    print()

def example_basic_usage():
    """Basic sandbox creation and code execution."""
    print("=== Example 1: Basic Usage ===")

    # Create a sandbox (uses E2B_API_KEY from environment)
    sandbox = E2BSandbox.create()

    # Run some Python code
    result = sandbox.run_code("print('Hello from sandbox!')")
    print(f"Output: {result.logs}")

    # Run code with variables
    result = sandbox.run_code("""
x = 10
y = 20
print(f"Sum: {x + y}")
    """)
    print(f"Output: {result.logs}")

    sandbox.close()
    print()


def example_context_manager():
    """Using context manager for automatic cleanup."""
    print("=== Example 2: Context Manager ===")

    # Context manager automatically closes sandbox
    with E2BSandbox.create() as sandbox:
        result = sandbox.run_code("""
import numpy as np
arr = np.array([1, 2, 3, 4, 5])
print(f"Array mean: {arr.mean()}")
        """)
        print(f"Output: {result.logs}")

    print("Sandbox automatically closed")
    print()


def example_file_operations():
    """Upload and download files to/from sandbox."""
    print("=== Example 3: File Operations ===")

    with E2BSandbox.create() as sandbox:
        # Create a local file to upload
        local_file = Path("test_input.txt")
        local_file.write_text("Hello from local file!")

        # Upload file to sandbox
        sandbox.upload_file(local_file, "/tmp/input.txt")
        print("File uploaded to sandbox")

        # Process the file in sandbox
        result = sandbox.run_code("""
with open('/tmp/input.txt', 'r') as f:
    content = f.read()

# Process and write output
with open('/tmp/output.txt', 'w') as f:
    f.write(content.upper())

print(f"Processed: {content}")
        """)
        print(f"Output: {result.logs}")

        # Download the result
        output_file = Path("test_output.txt")
        sandbox.download_file("/tmp/output.txt", output_file)
        print(f"Downloaded result: {output_file.read_text()}")

        # List files in sandbox
        files = sandbox.list_files("/tmp")
        print(f"Files in /tmp: {files}")

        # Cleanup local test files
        local_file.unlink()
        output_file.unlink()

    print()


def example_custom_config():
    """Create sandbox with custom configuration."""
    print("=== Example 4: Custom Configuration ===")

    # Create custom config
    config = SandboxConfig(
        timeout=600,  # 10 minutes
        api_key=None,  # Will use E2B_API_KEY from environment
        metadata={
            "project": "my-project",
            "user": "developer"
        }
    )

    with E2BSandbox.create(config) as sandbox:
        result = sandbox.run_code("""
import sys
print(f"Python version: {sys.version}")
print(f"Platform: {sys.platform}")
        """)
        print(f"Output: {result.logs}")

    print()


def example_data_analysis():
    """Example of using sandbox for data analysis."""
    print("=== Example 5: Data Analysis ===")

    with E2BSandbox.create() as sandbox:
        result = sandbox.run_code("""
import pandas as pd
import matplotlib.pyplot as plt

# Create sample data
data = {
    'name': ['Alice', 'Bob', 'Charlie', 'David'],
    'score': [85, 92, 78, 95]
}
df = pd.DataFrame(data)

print("DataFrame:")
print(df)
print(f"\\nAverage score: {df['score'].mean()}")

# Create a simple plot
plt.figure(figsize=(8, 6))
plt.bar(df['name'], df['score'])
plt.title('Student Scores')
plt.ylabel('Score')
plt.savefig('/tmp/scores.png')
print("\\nChart saved to /tmp/scores.png")
        """)
        print(f"Output: {result.logs}")

        # Download the generated plot
        sandbox.download_file("/tmp/scores.png", Path("scores.png"))
        print("Downloaded chart to scores.png")

    print()


def example_error_handling():
    """Example of proper error handling."""
    print("=== Example 6: Error Handling ===")

    try:
        with E2BSandbox.create() as sandbox:
            # This will cause an error
            result = sandbox.run_code("""
import non_existent_module
            """)

            if result.error:
                print(f"Execution error: {result.error}")
            else:
                print(f"Output: {result.logs}")

    except Exception as e:
        print(f"Exception occurred: {e}")

    print()


def main():
    """Run all examples."""
    print("SkillFS Sandbox Examples\n")
    print("Make sure E2B_API_KEY is set in your environment!\n")

    example_bash_usage()
    example_basic_usage()
    example_context_manager()
    example_file_operations()
    example_custom_config()
    example_data_analysis()
    example_error_handling()

    print("All examples completed!")


if __name__ == "__main__":
    main()
