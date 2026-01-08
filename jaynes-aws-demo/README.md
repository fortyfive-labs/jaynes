# Jaynes AWS Demo - MNIST Training

A complete example of using Jaynes to train PyTorch models on AWS EC2 with S3 code distribution and automatic output syncing.

## 📋 What This Demo Does

- Trains a simple CNN on MNIST dataset
- Demonstrates local → AWS deployment workflow
- Shows S3 code transfer and output syncing
- Supports spot instances for cost savings
- Handles spot termination gracefully
- Includes hyperparameter sweep example

## 🚀 Quick Start

### 1. Prerequisites

**Local Setup:**
```bash
# Install dependencies
pip install -r requirements.txt

# Configure AWS credentials
aws configure
# AWS Access Key ID: YOUR_KEY
# AWS Secret Access Key: YOUR_SECRET
# Default region: us-west-2
```

**AWS Setup:**

You need the following AWS resources:

1. **S3 Bucket** for code and outputs
   ```bash
   aws s3 mb s3://your-ml-bucket
   ```

2. **EC2 Key Pair**
   - Create in EC2 Console → Key Pairs
   - Download .pem file to `~/.ssh/`

3. **Security Group** with ports:
   - SSH (22) - for jaynes connection
   - Any application ports you need

4. **IAM Instance Profile** with permissions:
   - S3 read/write access
   - EC2 tag creation

5. **AMI ID** - Deep Learning AMI with Docker
   - Search for "Deep Learning AMI" in your region
   - Example: `ami-0abcdef1234567890`

### 2. Configure .jaynes.yml

Edit `.jaynes.yml` and update:

```yaml
# Line 13 & 23: Change YOUR-BUCKET-NAME
s3_prefix: s3://YOUR-BUCKET-NAME/jaynes-demo/code/{NOW:%Y-%m-%d}

# Lines 50-53: Update with your AWS resources
image_id: ami-0abcdef1234567890              # Your Deep Learning AMI
key_name: your-ec2-keypair                   # Your EC2 keypair name
security_group: your-sg-id                   # Your security group ID
iam_instance_profile_arn: arn:aws:iam::123456789012:instance-profile/YourEC2Role
```

### 3. Test Locally First

```bash
# Run locally to verify code works
python launch.py --mode local --epochs 2

# Or run training directly
python train.py --epochs 2
```

### 4. Deploy to AWS

```bash
# Test on small CPU instance first (cheap!)
python launch.py --mode debug --epochs 2

# Run on GPU spot instance
python launch.py --mode gpu --epochs 10

# Run on larger V100 GPU
python launch.py --mode gpu_large --epochs 10
```

## 📊 Execution Modes

| Mode | Instance Type | GPU | Cost/hr (spot) | Use Case |
|------|---------------|-----|----------------|----------|
| `local` | Your machine | - | Free | Development |
| `debug` | t3.medium | None | ~$0.04 | Testing deployment |
| `gpu` | g4dn.xlarge | 1x T4 | ~$0.20 | Quick GPU training |
| `gpu_large` | p3.2xlarge | 1x V100 | ~$1.00 | Serious training |
| `multi_gpu` | p3.8xlarge | 4x V100 | ~$4.00 | Large-scale training |

## 🔄 How It Works

### Workflow

```
┌─────────────┐     ┌──────────┐     ┌──────────┐
│  Your Code  │────▶│    S3    │────▶│   EC2    │
│   (Local)   │     │  Bucket  │     │ Instance │
└─────────────┘     └──────────┘     └──────────┘
                          │                │
                          │                │
                    ┌─────▼────────────────▼─────┐
                    │   Training Results (S3)    │
                    └────────────────────────────┘
```

### Step by Step

1. **Local**: Jaynes tars your code directory
2. **Upload**: Uploads tar to S3 bucket
3. **Launch**: Launches EC2 instance via boto3
4. **Download**: EC2 downloads code from S3
5. **Execute**: Runs Docker container with your code
6. **Sync**: Outputs sync to S3 every 15 seconds
7. **Terminate**: Instance shuts down when done

## 💡 Usage Examples

### Single Training Run

```bash
python launch.py --mode gpu --lr 0.001 --epochs 10
```

### Hyperparameter Sweep

```bash
# Launches 9 instances (3 LRs × 3 batch sizes)
python launch.py --mode gpu --sweep
```

### Custom Training

```python
import jaynes
from train import train

jaynes.config(mode="gpu")
jaynes.run(train,
           experiment_name="my-experiment",
           lr=0.0001,
           batch_size=128,
           epochs=20)
jaynes.listen()
```

## 📁 Project Structure

```
jaynes-aws-demo/
├── .jaynes.yml          # Jaynes configuration
├── train.py             # Training script
├── launch.py            # Launch script
├── requirements.txt     # Python dependencies
├── README.md            # This file
└── outputs/             # Training outputs (created automatically)
    ├── best_model.pth   # Best model checkpoint
    └── results.json     # Training metrics
```

## 🔍 Monitoring & Outputs

### Check S3 Outputs

```bash
# List all runs
aws s3 ls s3://your-bucket/jaynes-demo/outputs/

# Download specific run outputs
aws s3 cp s3://your-bucket/jaynes-demo/outputs/2024-01-15/abc-123/ ./results/ --recursive
```

### EC2 Instance Management

```bash
# List running instances
aws ec2 describe-instances --filters "Name=tag:Project,Values=jaynes-demo" \
  --query 'Reservations[*].Instances[*].[InstanceId,State.Name,InstanceType]' \
  --output table

# Terminate instance manually
aws ec2 terminate-instances --instance-ids i-1234567890abcdef0
```

### View Logs

After job completes, outputs are synced to:
```
s3://YOUR-BUCKET/jaynes-demo/outputs/YYYY-MM-DD/UUID/
├── best_model.pth
└── results.json
```

## ⚙️ Advanced Configuration

### Add Weights & Biases Logging

```python
# In launch.py
jaynes.run(train,
           experiment_name="mnist-wandb",
           lr=0.001,
           epochs=10,
           use_wandb=True)  # Enable W&B
```

### Custom Docker Image

Edit `.jaynes.yml`:
```yaml
runner: !runners.Docker
  image: "your-dockerhub-username/your-image:tag"
  startup: "pip install your-custom-deps"
```

### Multi-Region Support

```yaml
# Add to .jaynes.yml
modes:
  gpu_eu:
    mounts: [*code_mount, *output_mount]
    runner: *docker_gpu_runner
    launch:
      <<: *ec2_launch
      region: eu-west-1  # Ireland
      instance_type: g4dn.xlarge
```

## 💰 Cost Estimates

**Example Training Run:**
- Instance: g4dn.xlarge spot (~$0.20/hr)
- Training time: 15 minutes
- Cost: ~$0.05

**Hyperparameter Sweep (9 runs):**
- 9 × g4dn.xlarge spot (~$0.20/hr)
- 10 minutes each
- Total cost: ~$0.30

**S3 Storage:**
- Code tarball: ~1 MB
- Outputs per run: ~5 MB
- Monthly storage cost: negligible

## 🐛 Troubleshooting

### Error: "boto3 not installed"
```bash
pip install boto3
```

### Error: "AWS credentials not found"
```bash
aws configure
# Or export environment variables:
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
```

### Error: "Spot instance terminated"
- Increase `spot_price` in `.jaynes.yml`
- Or use on-demand: set `spot_price: null`

### Error: "S3 access denied"
- Check IAM instance profile has S3 permissions
- Verify bucket name is correct

### Training hangs downloading MNIST
- First run downloads dataset to `/tmp/mnist_data`
- Subsequent runs reuse cached data
- Can pre-download to Docker image for faster startup

## 📚 Next Steps

- **Add your own model**: Replace `SimpleCNN` in `train.py`
- **Use your dataset**: Modify data loading in `train.py`
- **Distributed training**: Use `multi_gpu` mode with DDP
- **Add experiment tracking**: Enable W&B or MLflow
- **Schedule regular training**: Use AWS Lambda + jaynes

## 🔗 Resources

- [Jaynes Documentation](https://jaynes.readthedocs.io/)
- [Jaynes GitHub](https://github.com/episodeyang/jaynes)
- [AWS EC2 Pricing](https://aws.amazon.com/ec2/pricing/)
- [AWS Spot Instance Pricing](https://aws.amazon.com/ec2/spot/pricing/)

## 📝 License

This demo is provided as-is for educational purposes.

---

**Happy Training! 🚀**
