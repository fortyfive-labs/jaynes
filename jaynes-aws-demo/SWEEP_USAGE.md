# Hyperparameter Sweep Usage Guide

This guide explains how to use the sweep feature in `launch_sweep.py` to run multiple training jobs with different hyperparameters.

## Prerequisites

**Python 3.10+ Required:** The scripts use params-proto which requires Python 3.10 or higher.

```bash
# Check your Python version
python3 --version

# If Python 3.9 or lower, use Python 3.11+ explicitly:
python3.11 launch_sweep.py --help
python3.12 launch_sweep.py --help
```

## Three Ways to Launch Jobs

### 1. Simple Jobs (Default)
Launch N identical jobs with default hyperparameters:

```bash
python3.11 launch_sweep.py --num-jobs 10 --max-concurrent 5 --mode gpu
```

This creates 10 jobs named `mnist-job-000`, `mnist-job-001`, etc., all with the same hyperparameters.

### 2. Grid Search
Run a predefined grid search over learning rates and batch sizes:

```bash
python3.11 launch_sweep.py --grid-search --max-concurrent 5 --mode gpu
```

This generates all combinations from the grid defined in the code:
- Learning rates: [0.01, 0.001, 0.0001]
- Batch sizes: [32, 64, 128]
- Total: 9 experiments

### 3. Custom Sweep Configuration (Recommended)
Use a YAML file to define your experiments:

```bash
python3.11 launch_sweep.py --sweep sweep_simple.yaml --max-concurrent 3 --mode gpu
```

## Sweep Configuration Format

Create a YAML file with this structure:

```yaml
experiments:
  - name: experiment-1
    lr: 0.001
    batch_size: 64
    epochs: 5
    use_wandb: false

  - name: experiment-2
    lr: 0.01
    batch_size: 128
    epochs: 5
    use_wandb: false
```

### Required Fields
Each experiment can have these parameters:
- `name` (optional): Experiment name, defaults to `sweep-XXX`
- `lr` (float): Learning rate
- `batch_size` (int): Training batch size
- `epochs` (int): Number of training epochs
- `use_wandb` (bool): Whether to use Weights & Biases logging

## Example Sweep Files

### Simple Sweep (`sweep_simple.yaml`)
3 experiments testing different hyperparameter combinations:

```bash
python3.11 launch_sweep.py --sweep sweep_simple.yaml --mode gpu --max-concurrent 3
```

### Full Sweep (`sweep.yaml`)
12 experiments covering:
- Learning rate sweep
- Batch size sweep
- Grid search combinations
- Longer training runs

```bash
python3.11 launch_sweep.py --sweep sweep.yaml --mode gpu --max-concurrent 5
```

## Concurrency Control

The `--max-concurrent` flag limits how many EC2 instances run simultaneously:

```bash
# Conservative: max 3 instances
python3.11 launch_sweep.py --sweep sweep.yaml --max-concurrent 3 --mode gpu

# Aggressive: max 10 instances
python3.11 launch_sweep.py --sweep sweep.yaml --max-concurrent 10 --mode gpu
```

The script automatically:
1. Launches jobs up to the concurrency limit
2. Polls running instances every `--check-interval` seconds (default: 30s)
3. Launches new jobs as instances complete and terminate
4. Waits until all jobs are launched

## Execution Modes

Choose your instance type with `--mode`:

| Mode | Instance Type | GPU | Cost (spot) |
|------|---------------|-----|-------------|
| `gpu` | g4dn.xlarge | 1x T4 | ~$0.16/hr |
| `gpu_large` | g5.xlarge | 1x A10G | ~$0.30/hr |
| `multi_gpu` | g4dn.12xlarge | 4x T4 | ~$1.17/hr |

Example:
```bash
# Use larger GPU for faster training
python3.11 launch_sweep.py --sweep sweep.yaml --mode gpu_large --max-concurrent 5
```

## Monitoring

While the sweep runs, monitor your jobs:

```bash
# In another terminal
python3.11 monitor_jobs.py --watch --cost

# Or check once
python3.11 monitor_jobs.py --cost
```

## Cost Management

### Cost Estimation
Before running a sweep, estimate the cost:

```yaml
# sweep_simple.yaml has 3 experiments, each ~5 minutes
# On g4dn.xlarge (spot): $0.16/hr
# Total: 3 experiments × 5 min × $0.16/hr ÷ 60 min ≈ $0.04
```

### Tips for Cost Control
1. **Start small**: Test with `sweep_simple.yaml` first
2. **Use concurrency limits**: `--max-concurrent 3` prevents runaway costs
3. **Use spot instances**: Configure `spot_price` in `.jaynes.yml`
4. **Monitor actively**: Use `monitor_jobs.py --watch --cost`
5. **Auto-termination**: Instances terminate automatically after training (configured in `.jaynes.yml`)

## Complete Example Workflow

```bash
# 1. Create your sweep configuration
cat > my_sweep.yaml <<EOF
experiments:
  - name: test-lr-high
    lr: 0.01
    batch_size: 64
    epochs: 3
    use_wandb: false

  - name: test-lr-low
    lr: 0.0001
    batch_size: 64
    epochs: 3
    use_wandb: false
EOF

# 2. Launch the sweep
python3.11 launch_sweep.py --sweep my_sweep.yaml --mode gpu --max-concurrent 2

# 3. Monitor in another terminal
python3.11 monitor_jobs.py --watch --cost

# 4. Check results (stored in S3)
aws s3 ls s3://YOUR-BUCKET-NAME/outputs/ --recursive
```

## Troubleshooting

### "No running instances found"
- Check AWS credentials: `aws sts get-caller-identity`
- Verify region: `--region us-east-1`
- Check `.jaynes.yml` configuration

### "Waiting... (10/5 instances running)"
- Too many instances running
- Wait for some to complete, or terminate manually:
  ```bash
  aws ec2 describe-instances --filters "Name=tag:Project,Values=jaynes-demo" \
    --query "Reservations[*].Instances[*].[InstanceId,State.Name]"
  ```

### Jobs fail immediately
- Check logs in S3: `s3://YOUR-BUCKET-NAME/outputs/`
- Test locally first: `python3.11 train.py --lr 0.001 --batch-size 64 --epochs 1`
- Verify AMI has required dependencies

## Advanced Usage

### Custom Check Interval
Check for completed instances more/less frequently:

```bash
# Check every 10 seconds (more responsive)
python3.11 launch_sweep.py --sweep sweep.yaml --check-interval 10 --mode gpu

# Check every 60 seconds (less API calls)
python3.11 launch_sweep.py --sweep sweep.yaml --check-interval 60 --mode gpu
```

### Different AWS Regions
```bash
python3.11 launch_sweep.py --sweep sweep.yaml --region us-west-2 --mode gpu
```

### Programmatic Sweep Generation
Instead of manually writing YAML, generate it:

```python
import yaml

experiments = []
for lr in [0.01, 0.001, 0.0001]:
    for bs in [32, 64, 128]:
        experiments.append({
            'name': f'mnist-lr{lr}-bs{bs}',
            'lr': lr,
            'batch_size': bs,
            'epochs': 5,
            'use_wandb': False
        })

with open('generated_sweep.yaml', 'w') as f:
    yaml.dump({'experiments': experiments}, f, default_flow_style=False)
```

Then run:
```bash
python3.11 launch_sweep.py --sweep generated_sweep.yaml --mode gpu
```
