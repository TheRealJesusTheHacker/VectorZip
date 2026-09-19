import time
import os
from src.compressor import compress_file

def run_benchmark(file_path):
    print("Starting benchmark for: {}".format(file_path))
    
    # 1. Setup
    if not os.path.exists(file_path):
        with open(file_path, "w") as f:
            f.write("VectorZip - high performance compression test. " * 100000)
    
    # 2. Execution
    start = time.perf_counter()
    output = compress_file(file_path)
    end = time.perf_counter()
    
    # 3. Report
    size_orig = os.path.getsize(file_path)
    size_comp = os.path.getsize(output)
    print("Compression complete in: {:.4f} seconds".format(end - start))
    if size_comp:
        print("Compression ratio: {:.2f}x".format(size_orig / size_comp))
    else:
        print("Compression ratio: n/a (empty output)")

if __name__ == "__main__":
    run_benchmark("benchmark_test.txt")
