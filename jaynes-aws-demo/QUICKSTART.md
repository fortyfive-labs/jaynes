# Quick Start Guide

## 1. Setup (5 minutes)

```bash
# Install dependencies
pip install -r requirements.txt

# Configure AWS
aws configure
```

## 2. Update Configuration

Edit `.jaynes.yml` - replace these values:

```yaml
# Line 13 & 23: Your S3 bucket
s3_prefix: s3://YOUR-BUCKET/jaynes-demo/code/{NOW:%Y-%m-%d}

# Lines 50-53: Your AWS resources
image_id: ami-XXXXXXXXXXXXXXXXX      # Deep Learning AMI
key_name: your-keypair-name          # EC2 keypair
security_group: sg-XXXXXXXXXXXXXXXXX # Security group
iam_instance_profile_arn: arn:aws:iam::XXXX:instance-profile/YourRole
```

## 3. Find Your AWS Resources

### S3 Bucket
```bash
aws s3 mb s3://my-ml-bucket
```

### AMI ID
```bash
# Find Deep Learning AMI in your region
aws ec2 describe-images \
  --owners amazon \
  --filters "Name=name,Values=Deep Learning AMI (Ubuntu 20.04)*" \
  --query 'Images[0].ImageId' \
  --output text
```

### Key Pair
- Create in EC2 Console → Key Pairs
- Download .pem to ~/.ssh/

### Security Group
```bash
# Create security group
aws ec2 create-security-group \
  --group-name jaynes-demo \
  --description "Jaynes ML training"

# Allow SSH
aws ec2 authorize-security-group-ingress \
  --group-name jaynes-demo \
  --protocol tcp \
  --port 22 \
  --cidr 0.0.0.0/0
```

### IAM Role
Create role with this policy:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:*"],
      "Resource": ["arn:aws:s3:::YOUR-BUCKET/*"]
    },
    {
      "Effect": "Allow",
      "Action": ["ec2:CreateTags"],
      "Resource": "*"
    }
  ]
}
```

## 4. Test & Deploy

```bash
# Test locally
python launch.py --mode local --epochs 2

# Test on AWS CPU (cheap!)
python launch.py --mode debug --epochs 2

# GPU training
python launch.py --mode gpu --epochs 10
```

## 5. Check Results

```bash
# View S3 outputs
aws s3 ls s3://YOUR-BUCKET/jaynes-demo/outputs/

# Download results
aws s3 cp s3://YOUR-BUCKET/jaynes-demo/outputs/2024-01-07/abc-123/ ./results/ --recursive
```

Done! 🎉
