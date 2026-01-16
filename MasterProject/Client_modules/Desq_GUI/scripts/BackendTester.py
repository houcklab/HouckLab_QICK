"""
===========================
test_backend_standalone.py
===========================
Simple standalone test for BackendDesq that doesn't require the full Desq infrastructure.

Place this file in the same directory as BackendDesq.py and run it:
    python test_backend_standalone.py

This will test:
1. Backend loads correctly
2. Figures are captured by sink
3. No OS windows appear
4. Thread isolation works
"""

import os
import sys
import threading
import time

# Ensure we can import BackendDesq from the same directory
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Set backend BEFORE importing matplotlib
os.environ['MPLBACKEND'] = 'module://BackendDesq'

print("=" * 60)
print("BackendDesq Standalone Test")
print("=" * 60)

# =============================================================================
# Test 1: Backend loads
# =============================================================================
print("\n[TEST 1] Loading backend...")
try:
    import matplotlib

    matplotlib.use('module://BackendDesq', force=True)

    backend = matplotlib.get_backend()
    print(f"  Current backend: {backend}")

    if 'backenddesq' in backend.lower():
        print("  ✓ Backend loaded successfully!")
    else:
        print(f"  ✗ Wrong backend: {backend}")
        sys.exit(1)
except Exception as e:
    print(f"  ✗ Failed to load backend: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# =============================================================================
# Test 2: Import backend functions
# =============================================================================
print("\n[TEST 2] Importing backend functions...")
try:
    from BackendDesq import (
        set_plot_sink, get_plot_sink, clear_plot_sink,
        FigureCaptureSink, FigureCanvasDesq, FigureManagerDesq
    )

    print("  ✓ All functions imported successfully!")
except ImportError as e:
    print(f"  ✗ Import failed: {e}")
    sys.exit(1)

# =============================================================================
# Test 3: Figure capture
# =============================================================================
print("\n[TEST 3] Testing figure capture...")
try:
    import matplotlib.pyplot as plt

    # Create capture sink
    sink = FigureCaptureSink()
    set_plot_sink(sink)

    # Create a figure
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 4, 9], 'ro-')
    ax.set_title("Test Figure")

    # Draw it (this should trigger the sink)
    fig.canvas.draw()

    # Check capture
    captured = sink.figures
    print(f"  Captured {len(captured)} figure(s)")

    if len(captured) == 1:
        print("  ✓ Figure captured successfully!")
    else:
        print("  ✗ Figure not captured")

    # Cleanup
    clear_plot_sink()
    plt.close('all')

except Exception as e:
    print(f"  ✗ Test failed: {e}")
    import traceback

    traceback.print_exc()

# =============================================================================
# Test 4: plt.show() doesn't block
# =============================================================================
print("\n[TEST 4] Testing plt.show() non-blocking...")
try:
    sink = FigureCaptureSink()
    set_plot_sink(sink)

    plt.figure()
    plt.plot([1, 2], [1, 2])

    # This should return immediately (not block)
    start = time.time()
    plt.show()
    elapsed = time.time() - start

    print(f"  plt.show() returned in {elapsed:.3f}s")

    if elapsed < 1.0:
        print("  ✓ plt.show() non-blocking!")
    else:
        print("  ⚠ plt.show() took longer than expected")

    captured = sink.figures
    print(f"  Captured {len(captured)} figure(s) via show()")

    clear_plot_sink()
    plt.close('all')

except Exception as e:
    print(f"  ✗ Test failed: {e}")

# =============================================================================
# Test 5: Thread isolation
# =============================================================================
print("\n[TEST 5] Testing thread isolation...")
try:
    results = {'main': 0, 'worker': 0}


    def worker():
        worker_sink = FigureCaptureSink()
        set_plot_sink(worker_sink)

        fig, ax = plt.subplots()
        ax.plot([1, 2], [2, 1])
        fig.canvas.draw()

        results['worker'] = len(worker_sink.figures)
        clear_plot_sink()
        plt.close(fig)


    # Main thread sink
    main_sink = FigureCaptureSink()
    set_plot_sink(main_sink)

    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [3, 2, 1])
    fig.canvas.draw()

    # Run worker
    t = threading.Thread(target=worker)
    t.start()
    t.join()

    results['main'] = len(main_sink.figures)

    print(f"  Main thread captured: {results['main']}")
    print(f"  Worker thread captured: {results['worker']}")

    if results['main'] == 1 and results['worker'] == 1:
        print("  ✓ Thread isolation working!")
    else:
        print("  ✗ Thread isolation failed")

    clear_plot_sink()
    plt.close('all')

except Exception as e:
    print(f"  ✗ Test failed: {e}")
    import traceback

    traceback.print_exc()

# =============================================================================
# Test 6: Custom sink callback
# =============================================================================
print("\n[TEST 6] Testing custom sink callback...")
try:
    callback_received = []


    def custom_sink(figure, event_type):
        callback_received.append((id(figure), event_type))
        print(f"    Custom sink called: figure={id(figure)}, event={event_type}")


    set_plot_sink(custom_sink)

    fig, ax = plt.subplots()
    ax.plot([1, 2], [1, 2])
    fig.canvas.draw()

    if len(callback_received) > 0:
        print(f"  ✓ Custom sink received {len(callback_received)} callback(s)!")
    else:
        print("  ✗ Custom sink not called")

    clear_plot_sink()
    plt.close('all')

except Exception as e:
    print(f"  ✗ Test failed: {e}")

# =============================================================================
# Summary
# =============================================================================
print("\n" + "=" * 60)
print("Test Complete!")
print("=" * 60)