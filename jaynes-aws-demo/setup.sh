#!/bin/bash
# Setup script for jaynes AWS demo

set -e

echo "=========================================="
echo "Jaynes AWS Demo - Setup Script"
echo "=========================================="
echo ""

# Check Python
echo "Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.8+"
    exit 1
fi
python_version=$(python3 --version)
echo "✓ Found: $python_version"
echo ""

# Check AWS CLI
echo "Checking AWS CLI..."
if ! command -v aws &> /dev/null; then
    echo "⚠ AWS CLI not found. Installing..."
    pip install awscli
else
    aws_version=$(aws --version)
    echo "✓ Found: $aws_version"
fi
echo ""

# Check AWS credentials
echo "Checking AWS credentials..."
if aws sts get-caller-identity &> /dev/null; then
    echo "✓ AWS credentials configured"
    aws sts get-caller-identity --query 'Account' --output text | xargs -I {} echo "  Account ID: {}"
else
    echo "❌ AWS credentials not configured"
    echo ""
    echo "Please run: aws configure"
    echo "You'll need:"
    echo "  - AWS Access Key ID"
    echo "  - AWS Secret Access Key"
    echo "  - Default region (e.g., us-west-2)"
    exit 1
fi
echo ""

# Install Python dependencies
echo "Installing Python dependencies..."
pip install -q -r requirements.txt
echo "✓ Dependencies installed"
echo ""

# Test local training
echo "Testing local training (2 epochs)..."
python train.py --epochs 2 --batch-size 32 > /tmp/jaynes_test.log 2>&1 &
TRAIN_PID=$!

# Show progress
for i in {1..10}; do
    if ps -p $TRAIN_PID > /dev/null; then
        echo -n "."
        sleep 2
    else
        break
    fi
done
echo ""

if wait $TRAIN_PID; then
    echo "✓ Local training test passed!"
else
    echo "❌ Local training test failed. Check /tmp/jaynes_test.log"
    exit 1
fi
echo ""

# Verify outputs
if [ -f "outputs/results.json" ]; then
    echo "✓ Found training outputs"
    rm -rf outputs/  # Clean up test outputs
else
    echo "⚠ No outputs found (unexpected)"
fi
echo ""

echo "=========================================="
echo "Setup Complete! ✓"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Edit .jaynes.yml and update:"
echo "   - S3 bucket name (lines 13, 23)"
echo "   - AWS resources (lines 50-53):"
echo "     • image_id (Deep Learning AMI)"
echo "     • key_name (EC2 keypair)"
echo "     • security_group"
echo "     • iam_instance_profile_arn"
echo ""
echo "2. Test deployment:"
echo "   python launch.py --mode local --epochs 2"
echo ""
echo "3. Deploy to AWS:"
echo "   python launch.py --mode debug --epochs 2  # Test on CPU"
echo "   python launch.py --mode gpu --epochs 10   # GPU training"
echo ""
echo "For help: python launch.py --help"
echo ""
