#!/usr/bin/env python3
"""
Monitor jaynes training jobs running on AWS EC2

Usage:
    # Watch all running jobs
    python monitor_jobs.py

    # Watch with auto-refresh
    python monitor_jobs.py --watch --interval 30

    # Get cost estimate
    python monitor_jobs.py --cost
"""
import boto3
import time
from datetime import datetime, timezone
from collections import defaultdict
from params_proto import proto


# Pricing (approximate as of 2026, us-east-1)
PRICING = {
    'g5.xlarge': {'on_demand': 1.006, 'spot': 0.30},
    'g4dn.xlarge': {'on_demand': 0.526, 'spot': 0.16},
    'g4dn.12xlarge': {'on_demand': 3.912, 'spot': 1.17},
    't3.medium': {'on_demand': 0.0416, 'spot': 0.0125}
}


def get_instances(region='us-east-1', project='jaynes-demo'):
    """Get all jaynes instances"""
    ec2 = boto3.client('ec2', region_name=region)

    response = ec2.describe_instances(
        Filters=[
            {'Name': 'instance-state-name',
             'Values': ['running', 'pending', 'shutting-down', 'stopping']},
            {'Name': 'tag:Project', 'Values': [project]}
        ]
    )

    instances = []
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instances.append(instance)

    return instances


def format_duration(seconds):
    """Format duration in human-readable format"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


def calculate_cost(instance_type, duration_hours, is_spot=False):
    """Calculate instance cost"""
    if instance_type not in PRICING:
        return 0.0

    price_per_hour = (PRICING[instance_type]['spot'] if is_spot
                      else PRICING[instance_type]['on_demand'])
    return duration_hours * price_per_hour


def display_instances(instances, show_cost=False):
    """Display instance information in a table"""
    if not instances:
        print("No running jaynes instances found")
        return

    now = datetime.now(timezone.utc)

    print("\n" + "=" * 120)
    print(f"{'ID':<20} {'Type':<16} {'State':<12} {'IP':<15} "
          f"{'Runtime':<12} {'Mode':<12} {'Cost':<10}")
    print("=" * 120)

    total_cost = 0.0
    stats = defaultdict(int)

    for instance in instances:
        instance_id = instance['InstanceId']
        instance_type = instance['InstanceType']
        state = instance['State']['Name']
        ip = instance.get('PublicIpAddress', 'N/A')

        # Get launch time and calculate runtime
        launch_time = instance['LaunchTime']
        runtime_seconds = (now - launch_time).total_seconds()
        runtime_hours = runtime_seconds / 3600
        runtime_str = format_duration(runtime_seconds)

        # Get tags
        tags = {tag['Key']: tag['Value']
                for tag in instance.get('Tags', [])}
        mode = tags.get('InstanceType', 'unknown')

        # Determine if spot instance
        is_spot = instance.get('InstanceLifecycle') == 'spot'
        spot_str = ' (spot)' if is_spot else ''

        # Calculate cost
        cost = calculate_cost(instance_type, runtime_hours, is_spot)
        total_cost += cost

        # Update stats
        stats[state] += 1
        stats[f'{instance_type}{spot_str}'] += 1

        cost_str = f"${cost:.3f}" if show_cost else ""

        print(f"{instance_id:<20} {instance_type + spot_str:<16} "
              f"{state:<12} {ip:<15} {runtime_str:<12} {mode:<12} {cost_str:<10}")

    print("=" * 120)
    print(f"\nTotal instances: {len(instances)}")

    print("\nBreakdown by state:")
    for state, count in sorted(stats.items()):
        if state in ['running', 'pending', 'shutting-down', 'stopping']:
            print(f"  {state}: {count}")

    print("\nBreakdown by instance type:")
    for itype, count in sorted(stats.items()):
        if itype not in ['running', 'pending', 'shutting-down', 'stopping']:
            print(f"  {itype}: {count}")

    if show_cost:
        print(f"\nEstimated total cost so far: ${total_cost:.2f}")
        print("(This is approximate and may not reflect exact AWS billing)")

    print()


def watch_instances(region='us-east-1', interval=30, show_cost=False):
    """Watch instances with auto-refresh"""
    try:
        while True:
            # Clear screen (works on Unix-like systems)
            print("\033[2J\033[H", end="")

            print(f"Monitoring jaynes instances (refreshing every {interval}s)")
            print(f"Time: {datetime.now():%Y-%m-%d %H:%M:%S}")

            instances = get_instances(region=region)
            display_instances(instances, show_cost=show_cost)

            print(f"Press Ctrl+C to stop monitoring...")

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\nMonitoring stopped")


def terminate_idle_instances(region='us-east-1', idle_threshold_minutes=10):
    """
    Terminate instances that have been running for a while but appear idle
    (This is a safety feature - use with caution!)
    """
    print(f"Checking for instances idle for >{idle_threshold_minutes} minutes...")

    instances = get_instances(region=region)
    ec2 = boto3.client('ec2', region_name=region)
    now = datetime.now(timezone.utc)

    to_terminate = []

    for instance in instances:
        if instance['State']['Name'] != 'running':
            continue

        launch_time = instance['LaunchTime']
        runtime_seconds = (now - launch_time).total_seconds()
        runtime_minutes = runtime_seconds / 60

        # Simple heuristic: if running for more than threshold and no recent activity
        # (This would need to be enhanced with actual activity monitoring)
        if runtime_minutes > idle_threshold_minutes:
            # Add more sophisticated checks here (e.g., CPU utilization, network traffic)
            print(f"Warning: {instance['InstanceId']} has been running for "
                  f"{runtime_minutes:.1f} minutes")

    if not to_terminate:
        print("No idle instances found")
    else:
        print(f"\nFound {len(to_terminate)} potentially idle instances")
        response = input("Terminate these instances? (yes/no): ")
        if response.lower() == 'yes':
            ec2.terminate_instances(InstanceIds=to_terminate)
            print(f"Terminated {len(to_terminate)} instances")


@proto.cli
def monitor(
    region: str = "us-east-1",  # AWS region
    watch: bool = False,  # Watch mode with auto-refresh
    interval: int = 30,  # Refresh interval in seconds (for watch mode)
    cost: bool = False,  # Show cost estimates
    terminate_idle: bool = False,  # Check and terminate idle instances
    idle_threshold: int = 10,  # Idle threshold in minutes
):
    """Monitor jaynes training jobs on AWS EC2"""
    if terminate_idle:
        terminate_idle_instances(
            region=region,
            idle_threshold_minutes=idle_threshold
        )
    elif watch:
        watch_instances(
            region=region,
            interval=interval,
            show_cost=cost
        )
    else:
        instances = get_instances(region=region)
        display_instances(instances, show_cost=cost)


if __name__ == "__main__":
    monitor()
