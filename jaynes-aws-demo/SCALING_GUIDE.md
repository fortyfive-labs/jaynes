# Jaynes AWS Scaling Guide

This guide covers how to scale up to many concurrent training instances with jaynes.

## Quick Start

### 1. Monitor Current Jobs

```bash
# Check running instances
python monitor_jobs.py

# Watch with auto-refresh
python monitor_jobs.py --watch --interval 30

# Show cost estimates
python monitor_jobs.py --cost --watch
```

### 2. Launch Multiple Jobs

```bash
# Launch 10 jobs with concurrency limit
python launch_sweep.py --num-jobs 10 --max-concurrent 5 --mode gpu

# Run grid search (9 configurations)
python launch_sweep.py --grid-search --max-concurrent 5 --mode gpu

# Launch on larger GPUs
python launch_sweep.py --num-jobs 20 --max-concurrent 10 --mode gpu_large
```

## Current AWS Limits

Your account has the following EC2 quotas in us-east-1:

| Resource | Limit | Usage |
|----------|-------|-------|
| On-Demand G instances | 768 vCPUs | - |
| Spot G instances | 64 vCPUs | - |

**Instance capacity:**
- g5.xlarge (4 vCPUs): 192 on-demand / 16 spot
- g4dn.xlarge (4 vCPUs): 192 on-demand / 16 spot
- g4dn.12xlarge (48 vCPUs): 16 on-demand / 1 spot

**To request quota increase:**
```bash
# Request 256 vCPU spot limit (64x increase)
aws service-quotas request-service-quota-increase \
  --service-code ec2 \
  --quota-code L-3819A6DF \
  --desired-value 256 \
  --region us-east-1
```

## Cost Management

### Pricing (us-east-1, approximate)

| Instance Type | GPU | On-Demand | Spot | Savings |
|---------------|-----|-----------|------|---------|
| g5.xlarge | A10G 24GB | $1.01/hr | $0.30/hr | 70% |
| g4dn.xlarge | T4 16GB | $0.53/hr | $0.16/hr | 70% |
| g4dn.12xlarge | 4x T4 | $3.91/hr | $1.17/hr | 70% |

### Cost Control Strategies

1. **Use Spot Instances** (70% savings)
   ```yaml
   # .jaynes.yml
   launch:
     spot_price: "0.60"  # Maximum willing to pay
   ```

2. **Set Concurrency Limits**
   ```bash
   # Limit to 10 concurrent instances
   python launch_sweep.py --max-concurrent 10
   ```

3. **Auto-Termination** (already configured)
   - Instances terminate 60s after training completes
   - Configured in `.jaynes.yml`:
     ```yaml
     launch:
       terminate_after: true
       delay: 60
     ```

4. **Monitor Costs**
   ```bash
   # Track estimated costs
   python monitor_jobs.py --cost

   # Set up billing alerts in AWS Console
   # https://console.aws.amazon.com/billing/home#/budgets
   ```

## Scaling Patterns

### Pattern 1: Hyperparameter Sweep

```python
import jaynes
from train import train

jaynes.config(mode='gpu')

# Define parameter grid
learning_rates = [0.01, 0.001, 0.0001]
batch_sizes = [32, 64, 128]

# Queue all jobs
for lr in learning_rates:
    for bs in batch_sizes:
        jaynes.add(
            train,
            experiment_name=f"sweep-lr{lr}-bs{bs}",
            lr=lr,
            batch_size=bs,
            epochs=5
        )

# Launch all at once
jaynes.execute()
```

### Pattern 2: Controlled Concurrency

```python
# Use launch_sweep.py for automatic concurrency control
configs = [
    {'name': f'job-{i}', 'lr': 0.001, 'batch_size': 64}
    for i in range(100)
]

launch_batch_with_concurrency_limit(
    configs,
    mode='gpu',
    max_concurrent=10  # Never exceed 10 instances
)
```

### Pattern 3: Different Instance Types

```python
# CPU instances for data preprocessing
jaynes.config(mode='debug')
for data_config in data_configs:
    jaynes.add(preprocess_data, **data_config)
jaynes.execute()

# GPU instances for training
jaynes.config(mode='gpu')
for train_config in train_configs:
    jaynes.add(train, **train_config)
jaynes.execute()
```

## Monitoring at Scale

### Real-time Monitoring

```bash
# Watch all running jobs
watch -n 30 'python monitor_jobs.py'

# Or use built-in watch mode
python monitor_jobs.py --watch --interval 30
```

### Check Job Status

```bash
# List all instances
aws ec2 describe-instances \
  --region us-east-1 \
  --filters "Name=tag:Project,Values=jaynes-demo" \
  --query 'Reservations[*].Instances[*].[InstanceId,State.Name,InstanceType]' \
  --output table
```

### SSH into Running Instances

```bash
# Get instance IP
INSTANCE_IP=$(aws ec2 describe-instances \
  --instance-ids i-xxxxxxxxx \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text)

# SSH and check logs
ssh -i ~/Downloads/EC2-computation-setup-test.pem ubuntu@$INSTANCE_IP \
  "sudo tail -100 /var/log/cloud-init-output.log"
```

## Handling Failures

### Issue 1: Spot Instance Interruption

**Problem:** Spot instances can be interrupted with 2-minute warning

**Solutions:**
1. Use on-demand for critical jobs:
   ```yaml
   spot_price: null  # Use on-demand
   ```

2. Implement checkpointing (add to train.py):
   ```python
   # Save checkpoint every N epochs
   if epoch % checkpoint_interval == 0:
       torch.save(model.state_dict(), f'checkpoint_epoch{epoch}.pth')
   ```

3. Monitor spot interruption notices:
   ```bash
   # On EC2 instance
   while true; do
       if curl -s http://169.254.169.254/latest/meta-data/spot/instance-action; then
           echo "Spot interruption warning!"
           # Save checkpoint and sync to S3
       fi
       sleep 5
   done
   ```

### Issue 2: Training Failures

**Problem:** Training fails but instance doesn't terminate

**Current Status:** ⚠️ Instance won't auto-terminate on errors

**Workaround:**
1. Monitor for idle instances:
   ```bash
   python monitor_jobs.py --terminate-idle --idle-threshold 20
   ```

2. Set maximum runtime in .jaynes.yml (requires jaynes modification)

3. Use AWS CloudWatch alarms for idle instances

### Issue 3: Quota Exceeded

**Problem:** Hit EC2 vCPU quota limit

**Solution:**
1. Request quota increase (see above)
2. Use concurrency limits:
   ```bash
   python launch_sweep.py --max-concurrent 10
   ```

## Best Practices

### 1. Start Small
```bash
# Test with 2-3 instances first
python launch_sweep.py --num-jobs 3 --max-concurrent 3 --mode gpu
```

### 2. Use Appropriate Instance Types

| Use Case | Recommended Instance |
|----------|---------------------|
| Quick experiments | g4dn.xlarge (T4) |
| Production training | g5.xlarge (A10G) |
| Large models | g4dn.12xlarge (4x T4) |
| Debugging | t3.medium (CPU) |

### 3. Organize Experiments

```python
# Use descriptive experiment names
experiment_name = f"{model_type}-{dataset}-lr{lr}-bs{bs}-{timestamp}"

# Tag instances for cost tracking
tags:
  Project: jaynes-demo
  Team: ml-research
  Experiment: hyperparameter-sweep-001
```

### 4. Cost Tracking

```bash
# Check daily costs
aws ce get-cost-and-usage \
  --time-period Start=2026-01-01,End=2026-01-08 \
  --granularity DAILY \
  --metrics BlendedCost \
  --group-by Type=TAG,Key=Project

# Set up budget alerts
aws budgets create-budget \
  --account-id YOUR_ACCOUNT_ID \
  --budget file://budget.json
```

### 5. Clean Up

```bash
# Check for running instances
python monitor_jobs.py

# Terminate all jaynes instances (use with caution!)
aws ec2 terminate-instances \
  --instance-ids $(aws ec2 describe-instances \
    --filters "Name=tag:Project,Values=jaynes-demo" "Name=instance-state-name,Values=running" \
    --query 'Reservations[*].Instances[*].InstanceId' \
    --output text)
```

## Example Workflows

### Workflow 1: Large Hyperparameter Sweep

```bash
# 1. Check current quota
aws service-quotas get-service-quota \
  --service-code ec2 \
  --quota-code L-3819A6DF \
  --region us-east-1

# 2. Launch sweep with concurrency control
python launch_sweep.py \
  --grid-search \
  --max-concurrent 10 \
  --mode gpu \
  --check-interval 30

# 3. Monitor in another terminal
python monitor_jobs.py --watch --cost
```

### Workflow 2: Multi-Stage Training

```bash
# Stage 1: Data preprocessing (CPU instances)
python launch.py --mode debug --epochs 0  # Custom preprocessing

# Stage 2: Initial training (small GPU)
python launch_sweep.py --num-jobs 5 --mode gpu

# Stage 3: Fine-tuning (large GPU)
python launch_sweep.py --num-jobs 3 --mode gpu_large
```

### Workflow 3: A/B Testing

```python
# Launch two versions simultaneously
configs_v1 = [{'name': f'v1-{i}', 'model_version': 'v1', ...} for i in range(10)]
configs_v2 = [{'name': f'v2-{i}', 'model_version': 'v2', ...} for i in range(10)]

all_configs = configs_v1 + configs_v2

launch_batch_with_concurrency_limit(
    all_configs,
    mode='gpu',
    max_concurrent=20
)
```

## Troubleshooting

### Issue: "Quota exceeded"
```bash
# Check current usage
python monitor_jobs.py

# Request increase
aws service-quotas request-service-quota-increase \
  --service-code ec2 \
  --quota-code L-3819A6DF \
  --desired-value 256
```

### Issue: "Spot capacity not available"
```bash
# Switch to on-demand
# Edit .jaynes.yml and set: spot_price: null

# Or try different availability zones
launch:
  availability_zone: us-east-1b  # Try different zones
```

### Issue: Jobs hanging after completion
```bash
# Check if instances are terminating
python monitor_jobs.py

# Manually terminate if needed
aws ec2 terminate-instances --instance-ids i-xxxxxxxxx
```

## Additional Resources

- [AWS EC2 Pricing](https://aws.amazon.com/ec2/pricing/)
- [AWS Service Quotas](https://console.aws.amazon.com/servicequotas/)
- [Jaynes Documentation](https://github.com/geyang/jaynes)
- [AWS Cost Explorer](https://console.aws.amazon.com/cost-management/)

## Summary

To scale to many instances:

1. ✅ **Check quotas** - Ensure you have enough vCPU capacity
2. ✅ **Use spot instances** - Save 70% on costs
3. ✅ **Set concurrency limits** - Use `launch_sweep.py` to control costs
4. ✅ **Monitor actively** - Use `monitor_jobs.py` to track jobs
5. ✅ **Auto-terminate** - Already configured in `.jaynes.yml`
6. ✅ **Start small** - Test with 2-3 instances first
7. ✅ **Clean up** - Verify all instances terminate properly

Your current setup supports:
- **Spot instances**: Up to 16 concurrent g5.xlarge or g4dn.xlarge
- **On-demand instances**: Up to 192 concurrent g5.xlarge or g4dn.xlarge
- **Auto-termination**: 60 seconds after training completes
- **Cost tracking**: Estimated with `monitor_jobs.py --cost`
