# params-proto Migration

All demo scripts have been converted from argparse to params-proto for cleaner, more declarative CLI interfaces.

## Changes Made

### 1. train.py
**Before:**
```python
parser = argparse.ArgumentParser(description='Train MNIST model')
parser.add_argument('--lr', type=float, default=0.001, help='Learning rate')
parser.add_argument('--batch-size', type=int, default=64, help='Batch size')
# ... more arguments
args = parser.parse_args()
train(experiment_name=args.experiment_name, lr=args.lr, ...)
```

**After:**
```python
from params_proto import proto

@proto.cli
def main(
    experiment_name: str = "mnist-demo",  # Experiment name
    lr: float = 0.001,  # Learning rate
    batch_size: int = 64,  # Batch size
    # ... more parameters
):
    """Train MNIST model"""
    train(experiment_name=experiment_name, lr=lr, ...)

main()
```

### 2. launch.py
Converted to use `@proto.cli` with inline help comments for:
- `mode`: Execution mode selection
- `sweep`: Hyperparameter sweep flag
- `lr`, `batch_size`, `epochs`: Training parameters

### 3. launch_sweep.py
Converted to use `@proto.cli` with inline help comments for:
- `mode`: Execution mode
- `num_jobs`: Number of jobs to launch
- `max_concurrent`: Concurrency limit
- `check_interval`: Instance check interval
- `region`: AWS region
- `grid_search`: Grid search flag

### 4. monitor_jobs.py
Converted to use `@proto.cli` with inline help comments for:
- `region`: AWS region
- `watch`: Watch mode flag
- `interval`: Refresh interval
- `cost`: Cost estimation flag
- `terminate_idle`: Idle termination flag
- `idle_threshold`: Idle threshold in minutes

## Benefits

1. **Cleaner syntax**: Type hints and inline comments replace verbose argparse code
2. **Better help text**: Automatically generated from inline comments and docstrings
3. **Type safety**: Native Python type hints instead of argparse types
4. **Less boilerplate**: ~50% less code for the same functionality

## Usage

All CLI arguments remain the same, but now with underscore-to-dash conversion:

```bash
# train.py
python train.py --experiment-name mnist-test --lr 0.001 --batch-size 64

# launch.py
python launch.py --mode gpu --sweep

# launch_sweep.py
python launch_sweep.py --num-jobs 10 --max-concurrent 5 --mode gpu

# monitor_jobs.py
python monitor_jobs.py --watch --interval 30 --cost
```

## Requirements

- Python 3.10+ (for `type | None` syntax in params-proto)
- params-proto v3.x

The AWS EC2 instances use Python 3.11+ so they will work without issues.
