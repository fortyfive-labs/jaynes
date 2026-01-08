# Jaynes AWS Workflow - Complete Technical Deep Dive

This document explains in detail how jaynes orchestrates ML training on AWS EC2, from configuration loading to instance termination.

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Phase 1: Configuration & Setup](#phase-1-configuration--setup)
3. [Phase 2: Code Packaging](#phase-2-code-packaging)
4. [Phase 3: S3 Upload](#phase-3-s3-upload)
5. [Phase 4: EC2 Instance Launch](#phase-4-ec2-instance-launch)
6. [Phase 5: Remote Execution](#phase-5-remote-execution)
7. [Phase 6: Training Execution](#phase-6-training-execution)
8. [Phase 7: Output Syncing](#phase-7-output-syncing)
9. [Phase 8: Instance Termination](#phase-8-instance-termination)
10. [Data Flow Diagram](#data-flow-diagram)

---

## Architecture Overview

Jaynes follows a **"package-upload-launch-execute-sync-terminate"** pattern:

```
Local Machine          S3 Bucket              EC2 Instance
     │                     │                       │
     ├─[1. Config]─────────┤                       │
     ├─[2. Package]────────┤                       │
     ├─[3. Upload]────────>│                       │
     ├─[4. Launch EC2]─────┴──────────────────────>│
     │                                              ├─[5. Download Code]
     │                                              ├─[6. Setup Environment]
     │                                              ├─[7. Run Training]
     │                                              ├─[8. Sync Outputs]────>S3
     ├─[9. Listen/Wait]<──────────────────────────┤
     │                                              ├─[10. Terminate]
     └──────────────────────────────────────────────┘
```

---

## Phase 1: Configuration & Setup

### Entry Point
```python
# User code (e.g., launch.py)
import jaynes
from train import train

jaynes.config(mode='gpu')
jaynes.run(train, lr=0.001, batch_size=64)
```

### What Happens

#### 1.1 Find .jaynes.yml
**Location:** `jaynes/jaynes.py:62-75`

```python
@classmethod
def config_root(cls, config_path=None):
    if config_path is None:
        # Walk up directory tree looking for .jaynes.yml
        for d in cwd_ancestors():
            try:
                config_path, = glob.glob(d + "/.jaynes.yml")
                break
            except Exception:
                pass
```

**Process:**
- Starts from current working directory
- Walks up parent directories until `.jaynes.yml` is found
- Returns the directory containing `.jaynes.yml` and the config path
- This directory becomes `RUN.config_root` used for resolving relative paths

#### 1.2 Load Configuration
**Location:** `jaynes/jaynes.py:78-102`

**Process:**
1. **Register YAML Constructors:**
   - `!mounts.S3Code` → `jaynes.mounts.S3Code`
   - `!mounts.S3Output` → `jaynes.mounts.S3Output`
   - `!runners.Simple` → `jaynes.runners.Simple`
   - `!runners.Docker` → `jaynes.runners.Docker`

2. **Create Interpolation Context:**
```python
context = {
    'env': os.environ,        # Environment variables
    'now': datetime.now(),    # Current timestamp
    'uuid': uuid4(),          # Unique ID for this run
    'secret': {...}           # From .secret.yml if exists
}
```

3. **Parse YAML with String Interpolation:**
```yaml
# Example from .jaynes.yml
prefix: s3://my-bucket/code/{now:%Y-%m-%d}
# Becomes: s3://my-bucket/code/2024-01-08
```

#### 1.3 Apply Mode Configuration
**Location:** `jaynes/jaynes.py:145-153`

```python
if mode:
    modes = config.get('modes', {})
    config.update(modes[mode])  # Merge mode config into root
```

**What Gets Merged (for `mode='gpu'`):**
- `mounts`: [S3Code, S3Output]
- `runner`: Simple runner with GPU setup
- `launch`: EC2 config (instance type, spot price, etc.)

#### 1.4 Create Launcher
**Location:** `jaynes/jaynes.py:174-178`

```python
launch_type = launch_config["type"]  # "ec2"
cls.launcher = getattr(jaynes.launchers, launch_type)(**launch_config)
# Creates: jaynes.launchers.EC2(**launch_config)
```

**Result:** An `EC2` launcher instance is created with:
- region: us-east-1
- instance_type: g4dn.xlarge
- spot_price: "0.40"
- security_group, IAM role, tags, etc.

---

## Phase 2: Code Packaging

### 2.1 Mount Upload Triggered
**Location:** `jaynes/jaynes.py:109-115`

```python
@classmethod
def upload_mount(J, mounts, verbose=None, **host):
    for mount in mounts:
        if mount in J._uploaded:
            print('this package is already uploaded')
        else:
            J._uploaded.append(mount)
            mount.upload(verbose=verbose, **host)
```

### 2.2 S3Code Mount Processing
**Location:** `jaynes/mounts.py:92-182`

**Configuration Example:**
```yaml
- !mounts.S3Code &code_mount
  prefix: s3://my-bucket/code/{now:%Y-%m-%d}
  local_path: .
  host_path: /home/ubuntu/jaynes-demo/{now:%H%M%S.%f}
  container_path: /workspace
  pypath: true
  compress: true
  excludes: "--exclude='*__pycache__' --exclude='*.git'"
```

**Initialization:**

1. **Resolve Paths:**
```python
local_path = "."
local_abs = os.path.join(RUN.config_root, local_path)
# /Users/me/project

name = uuid4()  # e.g., "a1b2c3d4-..."
tar_name = f"{name}.tar"
local_tar = "/tmp/jaynes-mount/a1b2c3d4-....tar"
```

2. **Generate Upload Script (`local_script`):**
```bash
type gtar >/dev/null 2>&1 && alias tar=`which gtar`
mkdir -p /tmp/jaynes-mount
tar --exclude='*__pycache__' --exclude='*.git' -czf /tmp/jaynes-mount/a1b2c3d4.tar -C /Users/me/project .
aws s3 cp /tmp/jaynes-mount/a1b2c3d4.tar s3://my-bucket/code/2024-01-08/a1b2c3d4.tar --region us-east-1
```

3. **Generate Download Script (`host_setup`):**
```bash
aws s3 cp s3://my-bucket/code/2024-01-08/a1b2c3d4.tar /tmp/a1b2c3d4.tar
mkdir -p /home/ubuntu/jaynes-demo/172545.123456
tar -zxf /tmp/a1b2c3d4.tar -C /home/ubuntu/jaynes-demo/172545.123456
```

**Key Features:**
- **Compression:** Uses gzip if `compress: true` (reduces upload time)
- **Excludes:** Skips `__pycache__`, `.git`, `.idea`, etc.
- **Unique paths:** Each run gets timestamped directory to avoid conflicts
- **Tar flags:**
  - `-c`: create archive
  - `-z`: compress with gzip
  - `-f`: specify filename
  - `-C`: change to directory before archiving

---

## Phase 3: S3 Upload

### 3.1 Execute Local Upload Script
**Location:** `jaynes/mounts.py:18-21`

```python
def upload(self, verbose=None, **_):
    if self.local_script is None:
        return
    assert not check_call(dedent(self.local_script or ""), verbose=verbose, shell=True)
```

**What Happens:**
1. Creates `/tmp/jaynes-mount/` directory
2. Creates tar archive of your code:
   ```
   tar -czf /tmp/jaynes-mount/a1b2c3d4.tar -C /Users/me/project .
   ```
3. Uploads to S3:
   ```
   aws s3 cp /tmp/jaynes-mount/a1b2c3d4.tar s3://my-bucket/code/2024-01-08/a1b2c3d4.tar
   ```

**S3 Bucket Structure After Upload:**
```
s3://my-bucket/
├── code/
│   └── 2024-01-08/
│       └── a1b2c3d4.tar  (your code archive)
└── outputs/
    └── 2024-01-08/
        └── b2c3d4e5.../   (will contain results)
```

### 3.2 S3Output Mount Setup
**Location:** `jaynes/mounts.py:372-455`

**Configuration:**
```yaml
- !mounts.S3Output &output_mount
  container_path: /workspace/outputs
  prefix: s3://my-bucket/outputs/{now:%Y-%m-%d}/{uuid}/
  interval: 15
  sync_s3: true
```

**Generated `host_setup` Script:**
```bash
echo 'making main_log directory /tmp/jaynes_mounts/outputs'
mkdir -p /tmp/jaynes_mounts/outputs
echo "made main_log directory"

# Background process for continuous sync
while true; do
    echo "uploading..."
    aws s3 cp --recursive /tmp/jaynes_mounts/outputs s3://my-bucket/outputs/2024-01-08/uuid123/
    sleep 15
done & echo "sync /tmp/jaynes_mounts/outputs initiated"

# Background process for spot instance interruption
while true; do
    if [ -z $(curl -Is http://169.254.169.254/latest/meta-data/spot/termination-time | head -1 | grep 404 | cut -d \  -f 2) ]
    then
        logger "Running shutdown hook."
        aws s3 cp --recursive /tmp/jaynes_mounts/outputs s3://my-bucket/outputs/2024-01-08/uuid123/
        break
    else
        sleep 3
    fi
done & echo main_log sync initiated
```

**Key Features:**
- **Continuous Sync:** Uploads outputs every 15 seconds while training runs
- **Spot Protection:** Monitors for spot instance termination and does final upload
- **Background Process:** Runs in background via `&` so training can proceed

---

## Phase 4: EC2 Instance Launch

### 4.1 Add Runner
**Location:** `jaynes/jaynes.py:237-256`

```python
@classmethod
def add(cls, fn, *args, **kwargs):
    Runner, hydrated_config = cls.process_runner_config()
    runner = Runner(**hydrated_config, mounts=cls.mounts)
    runner.build(fn, *args, **kwargs)
    cls.launcher.add_runner(runner)
```

**What `runner.build()` Does:**

1. **Serialize Function & Arguments:**
```python
# Location: jaynes/runners.py:59-63
def build(self, fn, *args, **kwargs):
    encoded_thunk = serialize(fn, args, kwargs)
    # Encoded using cloudpickle into base64 string
    # Example: "gASVgwAAAAAAAACMCF9fbWFpbl9flIwFdHJhaW6Ug..."
```

2. **Create Execution Script:**
```python
entry_env = f"JAYNES_PARAMS={encoded_thunk}"
self.main_script = f"{entry_env} python -u -m jaynes.entry"
```

**Result:** The runner now contains:
- `setup_script`: Environment setup commands
- `run_script`: The actual training execution
- `post_script`: Cleanup commands

### 4.2 Generate Launch Script
**Location:** `jaynes/launchers/base_launcher.py:75-168`

```python
def make_launch_script(
    runners, mounts, unpack_on_host, type, launch_dir,
    terminate_after=False, delay=None, instance_name=None, **_
):
```

**Generated Script Structure:**

```bash
#!/bin/bash
set +o posix

# Setup logging
mkdir -p /home/ubuntu/jaynes-demo/172545.123456
JAYNES_LAUNCH_DIR=/home/ubuntu/jaynes-demo/172545.123456

# Auto-termination trap (NEW!)
cleanup() {
    EXIT_CODE=$?
    echo "Cleanup triggered (exit code: $EXIT_CODE)"
    sleep 60
    export REGION="$(wget -q -O - http://169.254.169.254/latest/meta-data/placement/region)"
    export EC2_INSTANCE_ID="`wget -q -O - http://169.254.169.254/latest/meta-data/instance-id`"
    aws ec2 terminate-instances --instance-ids $EC2_INSTANCE_ID --region $REGION
}
trap cleanup EXIT ERR INT TERM

{
    # Tag instance
    export REGION="$(wget -q -O - http://169.254.169.254/latest/meta-data/placement/region)"
    EC2_INSTANCE_ID="`wget -q -O - http://169.254.169.254/latest/meta-data/instance-id`"
    aws ec2 create-tags --resources $EC2_INSTANCE_ID --tags 'Key=Name,Value=mnist-training' --region $REGION

    # Download and extract code from S3
    aws s3 cp s3://my-bucket/code/2024-01-08/a1b2c3d4.tar /tmp/a1b2c3d4.tar
    mkdir -p /home/ubuntu/jaynes-demo/172545.123456
    tar -zxf /tmp/a1b2c3d4.tar -C /home/ubuntu/jaynes-demo/172545.123456

    # Setup S3 output sync (background processes)
    mkdir -p /home/ubuntu/jaynes-demo/outputs
    while true; do
        aws s3 cp --recursive /home/ubuntu/jaynes-demo/outputs s3://my-bucket/outputs/2024-01-08/uuid123/
        sleep 15
    done &

    # Runner setup script
    sudo chown -R ubuntu:ubuntu /home/ubuntu/jaynes-demo
    PYTHONPATH=/opt/pytorch/lib/python3.12/site-packages python3.12 -m pip install --user jaynes torchvision
    nvidia-smi

    # Main training execution
    cd /home/ubuntu/jaynes-demo/172545.123456
    PYTHONPATH=/opt/pytorch/lib/python3.12/site-packages:/home/ubuntu/.local/lib/python3.12/site-packages \
    OUTPUT_DIR=/home/ubuntu/jaynes-demo/outputs \
    DATA_DIR=/tmp/mnist_data \
    JAYNES_PARAMS=gASVgwAAAAAAAACMCF9fbWFpbl9... \
    python3.12 -u -m jaynes.entry

} > >(tee -a /home/ubuntu/jaynes-demo/172545.123456/jaynes-launch.log) 2> >(tee -a /home/ubuntu/jaynes-demo/172545.123456/jaynes-launch.err.log >&2)
```

**Key Components:**

1. **Trap Handler (Lines 7-14):** Ensures termination even on errors
2. **Instance Tagging (Lines 18-20):** Tags instance with name for tracking
3. **Code Download (Lines 22-24):** Downloads and extracts your code
4. **Output Sync (Lines 26-29):** Background sync to S3 every 15 seconds
5. **Environment Setup (Lines 31-34):** Installs dependencies, checks GPU
6. **Training Execution (Lines 36-41):** Runs your code via jaynes.entry
7. **Output Redirection (Lines 43):** Logs to both console and files

### 4.3 Launch EC2 Instance
**Location:** `jaynes/launchers/ec2_launch.py:47-100`

**For Spot Instance:**
```python
response = ec2.request_spot_instances(
    InstanceCount=1,
    LaunchSpecification={
        'ImageId': 'ami-03b12bb641e054c72',
        'InstanceType': 'g4dn.xlarge',
        'KeyName': 'my-keypair',
        'SecurityGroupIds': ['sg-12345'],
        'IamInstanceProfile': {'Arn': 'arn:aws:iam::...'},
        'UserData': base64.b64encode(launch_script.encode())
    },
    SpotPrice': "0.40"
)
```

**For On-Demand Instance:**
```python
response = ec2.run_instances(
    MaxCount=1, MinCount=1,
    ImageId='ami-03b12bb641e054c72',
    InstanceType='g5.xlarge',
    KeyName='my-keypair',
    SecurityGroupIds=['sg-12345'],
    IamInstanceProfile={'Arn': 'arn:aws:iam::...'},
    UserData=launch_script  # Direct, no base64
)
```

**UserData Script:** The entire launch script is passed as `UserData`, which EC2 automatically executes on first boot via `/var/lib/cloud/instance/user-data.txt`

---

## Phase 5: Remote Execution

### 5.1 EC2 Instance Boots

**Timeline:**
1. **T+0s:** EC2 instance starts booting
2. **T+30s:** Ubuntu loads, cloud-init starts
3. **T+45s:** cloud-init executes UserData script
4. **T+60s:** Script begins executing (logging starts)

**Log Location on Instance:**
```
/var/log/cloud-init-output.log  # All UserData output
/home/ubuntu/jaynes-demo/172545.123456/jaynes-launch.log      # stdout
/home/ubuntu/jaynes-demo/172545.123456/jaynes-launch.err.log  # stderr
```

### 5.2 Instance Tagging
**Lines 1-3 of launch script:**
```bash
export REGION="$(wget -q -O - http://169.254.169.254/latest/meta-data/placement/region)"
EC2_INSTANCE_ID="`wget -q -O - http://169.254.169.254/latest/meta-data/instance-id`"
aws ec2 create-tags --resources $EC2_INSTANCE_ID --tags 'Key=Name,Value=mnist-training' --region $REGION
```

**Purpose:**
- Tags instance with human-readable name
- Makes it easy to find in EC2 console
- Uses EC2 metadata service (169.254.169.254) to get instance info

### 5.3 Code Download & Extract
**Lines 4-6:**
```bash
aws s3 cp s3://my-bucket/code/2024-01-08/a1b2c3d4.tar /tmp/a1b2c3d4.tar
mkdir -p /home/ubuntu/jaynes-demo/172545.123456
tar -zxf /tmp/a1b2c3d4.tar -C /home/ubuntu/jaynes-demo/172545.123456
```

**Directory Structure After Extraction:**
```
/home/ubuntu/jaynes-demo/172545.123456/
├── train.py
├── launch.py
├── requirements.txt
├── jaynes-launch.log        (created by redirection)
└── jaynes-launch.err.log    (created by redirection)
```

### 5.4 Start Output Sync
**Lines 7-10 (background process):**
```bash
mkdir -p /home/ubuntu/jaynes-demo/outputs
while true; do
    aws s3 cp --recursive /home/ubuntu/jaynes-demo/outputs s3://my-bucket/outputs/2024-01-08/uuid123/
    sleep 15
done &
```

**Why Background:**
- Runs in parallel with training
- Continuously uploads outputs as they're created
- Ensures outputs survive spot interruptions
- Uses `&` to run in background

### 5.5 Environment Setup
**Lines 11-13:**
```bash
sudo chown -R ubuntu:ubuntu /home/ubuntu/jaynes-demo
PYTHONPATH=/opt/pytorch/lib/python3.12/site-packages python3.12 -m pip install --user jaynes torchvision
nvidia-smi
```

**Purpose:**
- Fix permissions (files owned by root from UserData)
- Install jaynes and dependencies in user space
- Verify GPU is accessible

---

## Phase 6: Training Execution

### 6.1 Entry Point
**Line 14-18 of launch script:**
```bash
cd /home/ubuntu/jaynes-demo/172545.123456
PYTHONPATH=/opt/pytorch/lib/python3.12/site-packages:/home/ubuntu/.local/lib/python3.12/site-packages \
OUTPUT_DIR=/home/ubuntu/jaynes-demo/outputs \
DATA_DIR=/tmp/mnist_data \
JAYNES_PARAMS=gASVgwAAAAAAAACMCF9fbWFpbl9fUwAAAC4uLg== \
python3.12 -u -m jaynes.entry
```

**Environment Variables Set:**
- `PYTHONPATH`: Makes imported packages findable
- `OUTPUT_DIR`: Where training saves results
- `DATA_DIR`: Where datasets are cached
- `JAYNES_PARAMS`: **Serialized function call** (pickled & base64)

### 6.2 Jaynes Entry Module
**Location:** `jaynes/entry.py` (not shown but critical)

**What It Does:**
```python
import os
import cloudpickle

# Get the serialized function from environment
encoded = os.environ['JAYNES_PARAMS']

# Deserialize: fn, args, kwargs
fn, args, kwargs = cloudpickle.loads(base64.b64decode(encoded))

# Execute the function
result = fn(*args, **kwargs)
```

**Example:**
```python
# Original call:
jaynes.run(train, lr=0.001, batch_size=64)

# Becomes on remote:
import train
train.train(lr=0.001, batch_size=64)
```

### 6.3 Training Execution

**Your `train.py` runs:**
```python
def train(lr=0.001, batch_size=64, epochs=5):
    # Load data
    train_dataset = datasets.MNIST(
        '/tmp/mnist_data',  # DATA_DIR from env
        train=True, download=True
    )

    # Train model
    for epoch in range(epochs):
        for batch in train_loader:
            # ... training loop ...

    # Save results
    torch.save(model.state_dict(), '/workspace/outputs/best_model.pth')
    with open('/workspace/outputs/results.json', 'w') as f:
        json.dump(results, f)
```

**Output Directory:**
```
/home/ubuntu/jaynes-demo/outputs/
├── best_model.pth
└── results.json
```

---

## Phase 7: Output Syncing

### 7.1 Continuous Background Sync

**Process Running Since Step 5.4:**
```bash
while true; do
    aws s3 cp --recursive /home/ubuntu/jaynes-demo/outputs s3://my-bucket/outputs/2024-01-08/uuid123/
    sleep 15
done
```

**Timeline:**
- **T+0s:** Training starts, outputs/ directory is empty
- **T+60s:** First checkpoint saved → `best_model.pth` created
- **T+75s:** (T+60+15) First sync uploads `best_model.pth` to S3
- **T+120s:** Training completes → `results.json` created
- **T+135s:** Final sync uploads `results.json` to S3

**S3 Structure:**
```
s3://my-bucket/outputs/2024-01-08/b2c3d4e5-uuid/
├── best_model.pth      (uploaded at T+75s)
└── results.json        (uploaded at T+135s)
```

### 7.2 Spot Instance Protection

**Additional Background Process:**
```bash
while true; do
    if [ -z $(curl -Is http://169.254.169.254/latest/meta-data/spot/termination-time | head -1 | grep 404 | cut -d \  -f 2) ]
    then
        # Spot termination detected!
        logger "Running shutdown hook."
        aws s3 cp --recursive /home/ubuntu/jaynes-demo/outputs s3://my-bucket/outputs/2024-01-08/uuid123/
        break
    else
        # No termination yet, check again in 3 seconds
        sleep 3
    fi
done
```

**How It Works:**
1. Polls EC2 metadata every 3 seconds
2. Checks for spot termination notice
3. When termination detected (2-minute warning):
   - Immediately does final S3 sync
   - Ensures latest outputs are saved
4. AWS terminates instance ~2 minutes after warning

**Metadata Endpoint Behavior:**
- **Normal:** Returns HTTP 404 (no termination)
- **Terminating:** Returns HTTP 200 with termination time

---

## Phase 8: Instance Termination

### 8.1 Normal Completion Path

**When Training Completes:**
1. `jaynes.entry` finishes executing
2. Script exits with code 0
3. **Trap handler catches EXIT signal:**
```bash
cleanup() {
    EXIT_CODE=$?  # Will be 0
    echo "Cleanup triggered (exit code: $EXIT_CODE)"
    sleep 60  # Wait for final S3 sync
    export REGION="$(wget -q -O - http://169.254.169.254/latest/meta-data/placement/region)"
    export EC2_INSTANCE_ID="`wget -q -O - http://169.254.169.254/latest/meta-data/instance-id`"
    aws ec2 terminate-instances --instance-ids $EC2_INSTANCE_ID --region $REGION
}
```

**Timeline:**
- **T+0s:** Training finishes
- **T+0s:** EXIT trap triggers → cleanup() called
- **T+0s-60s:** 60-second delay for final S3 syncs to complete
- **T+60s:** `aws ec2 terminate-instances` called
- **T+65s:** Instance begins shutting down
- **T+90s:** Instance fully terminated

### 8.2 Error Handling Path

**Scenario 1: Python Error During Training**
```python
# In train.py
def train(...):
    model = load_model()  # FileNotFoundError!
    # ... never reaches here
```

**What Happens:**
1. Python raises `FileNotFoundError`
2. `jaynes.entry` exits with code 1
3. **Trap catches ERR signal:**
```bash
trap cleanup EXIT ERR INT TERM
```
4. `cleanup()` runs → instance terminates after 60s
5. **Outputs saved so far are preserved in S3**

**Scenario 2: Out of Memory**
```bash
# Training process killed by OOM killer
Killed
```

**What Happens:**
1. Process killed by Linux kernel
2. Script exits with code 137 (128+9 for SIGKILL)
3. **Trap catches EXIT signal**
4. `cleanup()` runs → instance terminates
5. Partial outputs still saved to S3

**Scenario 3: User Interruption**
```bash
# User hits Ctrl+C on local machine during jaynes.listen()
# (Doesn't affect remote instance - it keeps running)
```

**What Happens:**
1. Local process interrupted
2. **Remote instance unaffected** (UserData script runs independently)
3. Training continues on EC2
4. Instance terminates normally when training completes

**Scenario 4: Spot Instance Interruption**
```bash
# AWS sends 2-minute warning
```

**What Happens:**
1. Spot protection process detects termination notice
2. Immediately runs final S3 sync
3. 2 minutes later, AWS forcibly terminates instance
4. **Cleanup trap may not run** (forceful SIGKILL)
5. But outputs already saved via spot protection sync

### 8.3 Termination Guarantees

**The trap ensures termination on:**
- ✅ Normal exit (exit 0)
- ✅ Python exceptions (exit 1)
- ✅ Command failures (exit non-zero)
- ✅ Script errors (set -e would cause early exit)
- ✅ SIGINT (Ctrl+C on remote)
- ✅ SIGTERM (kill command)
- ⚠️  SIGKILL (kill -9) - trap cannot catch this

**Delays:**
- **60 seconds** after training completes (for final sync)
- Configurable via `.jaynes.yml`:
```yaml
launch:
  terminate_after: true
  delay: 60  # Adjust this
```

---

## Phase 9: Local Machine (jaynes.listen)

### 9.1 Listen Function
**Location:** `jaynes/jaynes.py:309-329`

```python
def listen(timeout=None, interval=math.pi * 5, command=None, backoff_limit=None):
    """Just a for-loop, to keep this process connected to the ssh session"""

    cprint('Jaynes pipe-back is now listening...', "blue")

    if timeout:
        time.sleep(timeout)
    else:
        backoff = 0
        while backoff_limit is None or backoff_limit > backoff:
            if command is not None:
                status = os.system(command)
                if status == 0:
                    break
            time.sleep(interval)
            backoff += 1
```

**Purpose:**
- **Keep script running** on local machine
- Allows user to see that launch was successful
- Can optionally poll for completion (with `command`)

**Note:** This is **NOT** required for remote execution:
- EC2 instance runs independently
- UserData script continues even if local script exits
- Outputs are saved regardless

**Typical Usage:**
```python
jaynes.config(mode='gpu')
jaynes.run(train, lr=0.001)
jaynes.listen()  # Optional - just keeps local script alive
```

### 9.2 Monitoring Progress

**Option 1: Check S3 Outputs**
```bash
aws s3 ls s3://my-bucket/outputs/2024-01-08/ --recursive
# Shows files as they're uploaded every 15 seconds
```

**Option 2: SSH to Instance**
```bash
# Get instance IP
aws ec2 describe-instances --instance-ids i-1234567890abcdef0

# SSH and tail logs
ssh -i ~/keypair.pem ubuntu@1.2.3.4
tail -f /home/ubuntu/jaynes-demo/*/jaynes-launch.log
```

**Option 3: CloudWatch Logs** (if configured)
```bash
aws logs tail /aws/ec2/jaynes-demo --follow
```

---

## Data Flow Diagram

### Complete Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         LOCAL MACHINE                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  1. Load .jaynes.yml                                                 │
│     ├─ Parse YAML with constructors (!mounts.S3Code, !runners.Simple)│
│     ├─ Interpolate strings ({now:%Y-%m-%d}, {uuid})                 │
│     └─ Merge mode config (gpu, debug, etc.)                         │
│                                                                       │
│  2. Create Mounts                                                    │
│     ├─ S3Code: Generates tar of local code                          │
│     │   tar -czf /tmp/uuid.tar -C /path/to/code .                   │
│     │                                                                 │
│     └─ S3Output: Prepares sync scripts                              │
│         mkdir -p outputs; while true; do                             │
│           aws s3 cp --recursive outputs s3://bucket/; sleep 15       │
│         done &                                                        │
│                                                                       │
│  3. Upload to S3                                                     │
│     aws s3 cp /tmp/uuid.tar s3://bucket/code/2024-01-08/uuid.tar    │
│                                                                       │
│  4. Create Runner                                                    │
│     ├─ Serialize function: cloudpickle.dumps(train, (args,), kwargs) │
│     └─ Encode to base64: base64.b64encode(pickle_data)              │
│                                                                       │
│  5. Generate Launch Script                                           │
│     ├─ Add trap handler for auto-termination                        │
│     ├─ Include code download from S3                                │
│     ├─ Include environment setup                                     │
│     ├─ Include serialized function execution                        │
│     └─ Include output sync loops                                     │
│                                                                       │
│  6. Launch EC2                                                       │
│     ec2.run_instances(UserData=launch_script)                       │
│     OR                                                                │
│     ec2.request_spot_instances(UserData=base64(launch_script))      │
│                                                                       │
│  7. Listen (optional)                                                │
│     while True: sleep(interval)                                      │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Launch
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                              S3 BUCKET                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  code/2024-01-08/uuid.tar ◄──── (from local upload)                 │
│                                                                       │
│  outputs/2024-01-08/uuid/ ◄──── (from remote sync, every 15s)       │
│     ├─ checkpoint_epoch1.pth                                        │
│     ├─ checkpoint_epoch2.pth                                        │
│     ├─ best_model.pth                                                │
│     └─ results.json                                                  │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Download
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          EC2 INSTANCE                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  BOOT SEQUENCE:                                                      │
│  1. Instance starts (t=0s)                                           │
│  2. Ubuntu loads (t=30s)                                             │
│  3. cloud-init runs UserData script (t=45s)                         │
│                                                                       │
│  EXECUTION:                                                          │
│  ┌─────────────────────────────────────────────────────┐            │
│  │ Trap Handler (runs on ANY exit)                     │            │
│  │ cleanup() {                                          │            │
│  │   sleep 60; # wait for syncs                        │            │
│  │   aws ec2 terminate-instances --instance-ids $ID    │            │
│  │ }                                                     │            │
│  │ trap cleanup EXIT ERR INT TERM                       │            │
│  └─────────────────────────────────────────────────────┘            │
│                                                                       │
│  4. Tag instance with name                                           │
│     aws ec2 create-tags ...                                          │
│                                                                       │
│  5. Download & extract code                                          │
│     aws s3 cp s3://bucket/code/uuid.tar /tmp/                       │
│     tar -zxf /tmp/uuid.tar -C /home/ubuntu/jaynes-demo/             │
│                                                                       │
│  6. Start background sync processes                                  │
│     ┌────────────────────┐  ┌──────────────────────┐               │
│     │ Output Sync        │  │ Spot Protection      │               │
│     │ (every 15s)        │  │ (every 3s)           │               │
│     │                    │  │                      │               │
│     │ while true; do     │  │ while true; do       │               │
│     │   aws s3 cp ...    │  │   check termination  │               │
│     │   sleep 15         │  │   if terminating:    │               │
│     │ done &             │  │     s3 final sync    │               │
│     │                    │  │   sleep 3            │               │
│     └────────────────────┘  │ done &               │               │
│                              └──────────────────────┘               │
│                                                                       │
│  7. Setup environment                                                │
│     pip install jaynes torchvision                                   │
│     nvidia-smi                                                        │
│                                                                       │
│  8. Execute training                                                 │
│     cd /home/ubuntu/jaynes-demo/uuid/                                │
│     JAYNES_PARAMS=<pickled_function> python -m jaynes.entry         │
│       ├─ Deserialize: fn, args, kwargs = cloudpickle.loads(...)    │
│       ├─ Execute: fn(*args, **kwargs)                               │
│       └─ Write outputs to /home/ubuntu/jaynes-demo/outputs/        │
│                                                                       │
│  9. Training completes                                               │
│     ├─ EXIT trap triggers                                           │
│     ├─ cleanup() waits 60s for final syncs                          │
│     └─ Instance terminates itself                                    │
│                                                                       │
│  LOGS:                                                               │
│  ├─ /var/log/cloud-init-output.log (all UserData output)           │
│  ├─ jaynes-launch.log (stdout)                                      │
│  └─ jaynes-launch.err.log (stderr)                                  │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Key Takeaways

### 1. **Separation of Concerns**
- **Local:** Configuration, packaging, uploading, launching
- **S3:** Code distribution, output storage
- **Remote:** Execution, monitoring, cleanup

### 2. **Resilience Features**
- **Continuous sync:** Outputs saved every 15 seconds
- **Spot protection:** Final sync before termination
- **Auto-termination:** Guaranteed cleanup even on errors
- **Independent execution:** Remote continues if local disconnects

### 3. **Cost Optimization**
- **Spot instances:** 70% savings over on-demand
- **Auto-termination:** No runaway costs from stuck instances
- **Minimal data transfer:** Code compressed, outputs streamed

### 4. **Developer Experience**
- **Simple API:** `jaynes.config()` + `jaynes.run()`
- **No SSH required:** UserData handles everything
- **Automatic serialization:** Functions & args pickled seamlessly
- **Flexible configuration:** YAML with string interpolation

### 5. **Security Considerations**
- **IAM roles:** Instance uses IAM profile (no credentials needed)
- **Security groups:** Network access controlled
- **S3 bucket:** Private by default, temporary signed URLs
- **Code isolation:** Each run in unique directory

---

## Common Workflows

### Basic Training Run
```python
import jaynes
from train import train

jaynes.config(mode='gpu')
jaynes.run(train, lr=0.001, batch_size=64, epochs=10)
```

### Hyperparameter Sweep
```python
import jaynes
from train import train

jaynes.config(mode='gpu')

for lr in [0.01, 0.001, 0.0001]:
    for bs in [32, 64, 128]:
        jaynes.add(train, lr=lr, batch_size=bs, epochs=5)

jaynes.execute()  # Launches all at once
```

### Large-Scale Batch Jobs
```python
from launch_sweep import launch_batch_with_concurrency_limit

configs = [
    {'lr': 0.001, 'batch_size': 64, 'name': f'job-{i}'}
    for i in range(100)
]

launch_batch_with_concurrency_limit(
    configs,
    mode='gpu',
    max_concurrent=10  # Rate limiting
)
```

---

## Debugging Tips

### Check Instance Launched
```bash
aws ec2 describe-instances --filters "Name=tag:Project,Values=jaynes-demo"
```

### View Remote Logs
```bash
# Get instance IP
INSTANCE_IP=$(aws ec2 describe-instances --instance-ids i-xxx --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

# SSH and check logs
ssh -i ~/keypair.pem ubuntu@$INSTANCE_IP
sudo tail -f /var/log/cloud-init-output.log
```

### Check S3 Outputs
```bash
aws s3 ls s3://my-bucket/outputs/ --recursive --human-readable
```

### Monitor Costs
```bash
python monitor_jobs.py --cost --watch
```

---

## Conclusion

Jaynes provides a complete orchestration layer that handles:
1. ✅ Code packaging and distribution
2. ✅ Infrastructure provisioning
3. ✅ Remote execution
4. ✅ Output management
5. ✅ Cost optimization
6. ✅ Error handling and cleanup

All while maintaining a simple, Pythonic API that lets you focus on your ML code rather than infrastructure complexity.
