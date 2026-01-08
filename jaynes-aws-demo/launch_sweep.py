#!/usr/bin/env python3
"""
Large-scale job launcher with cost management and monitoring

Usage:
    # Launch 50 jobs with cost limits
    python launch_sweep.py --num-jobs 50 --max-concurrent 10 --mode gpu

    # Launch with specific configurations
    python launch_sweep.py --config experiments.yaml --mode gpu_large
"""
import jaynes
import time
import boto3
from datetime import datetime


def get_running_instances(region='us-east-1', project='jaynes-demo'):
    """Count currently running jaynes instances"""
    ec2 = boto3.client('ec2', region_name=region)
    response = ec2.describe_instances(
        Filters=[
            {'Name': 'instance-state-name', 'Values': ['running', 'pending']},
            {'Name': 'tag:Project', 'Values': [project]}
        ]
    )

    count = 0
    for reservation in response['Reservations']:
        count += len(reservation['Instances'])
    return count


def launch_batch_with_concurrency_limit(
    configs,
    mode='gpu',
    max_concurrent=10,
    check_interval=30,
    region='us-east-1'
):
    """
    Launch jobs in batches respecting concurrency limits

    Args:
        configs: List of dicts with experiment parameters
        mode: jaynes mode (gpu, gpu_large, multi_gpu)
        max_concurrent: Maximum concurrent instances
        check_interval: Seconds between checks
        region: AWS region
    """
    from train import train

    total_jobs = len(configs)
    launched = 0

    print(f"Launching {total_jobs} jobs with max {max_concurrent} concurrent instances")
    print(f"Mode: {mode}")
    print(f"Region: {region}")
    print("-" * 60)

    jaynes.config(mode=mode)

    for i, config in enumerate(configs):
        # Wait if we've hit the concurrency limit
        while get_running_instances(region=region) >= max_concurrent:
            print(f"[{datetime.now():%H:%M:%S}] Waiting... "
                  f"({get_running_instances(region=region)}/{max_concurrent} instances running)")
            time.sleep(check_interval)

        # Launch the job (use add + execute to avoid blocking)
        experiment_name = config.get('name', f'job-{i:03d}')
        print(f"[{datetime.now():%H:%M:%S}] Launching {experiment_name} "
              f"({i+1}/{total_jobs})")

        jaynes.add(
            train,
            experiment_name=experiment_name,
            **{k: v for k, v in config.items() if k != 'name'}
        )
        jaynes.execute()
        launched += 1

        # Brief delay to avoid rate limits and allow instance to start
        time.sleep(5)

    print("-" * 60)
    print(f"All {launched} jobs launched successfully!")
    print(f"Instances will auto-terminate after training completes")


def generate_grid_search_configs(param_grid):
    """Generate all combinations from parameter grid"""
    import itertools

    keys = param_grid.keys()
    values = param_grid.values()
    configs = []

    for combo in itertools.product(*values):
        config = dict(zip(keys, combo))
        # Generate a descriptive name
        name_parts = [f"{k[:2]}{v}" for k, v in config.items()
                      if k not in ['epochs', 'use_wandb']]
        config['name'] = f"mnist-{'_'.join(name_parts)}"
        configs.append(config)

    return configs


def main():
    from params_proto import proto

    @proto.cli
    def launch_sweep(
        mode: str = "gpu",  # Execution mode: gpu, gpu_large, multi_gpu
        num_jobs: int = 10,  # Number of jobs to launch
        max_concurrent: int = 10,  # Maximum concurrent instances
        check_interval: int = 30,  # Seconds between instance checks
        region: str = "us-east-1",  # AWS region
        grid_search: bool = False,  # Run grid search over hyperparameters
    ):
        """Launch large-scale jaynes training jobs"""
        # Validate mode
        valid_modes = ['gpu', 'gpu_large', 'multi_gpu']
        if mode not in valid_modes:
            raise ValueError(f"mode must be one of {valid_modes}")

        # Generate job configurations
        if grid_search:
            print("Running grid search...")
            param_grid = {
                'lr': [0.01, 0.001, 0.0001],
                'batch_size': [32, 64, 128],
                'epochs': [5],
                'use_wandb': [False]
            }
            configs = generate_grid_search_configs(param_grid)
            print(f"Generated {len(configs)} configurations")
        else:
            # Generate simple numbered jobs
            configs = [
                {
                    'name': f'mnist-job-{i:03d}',
                    'lr': 0.001,
                    'batch_size': 64,
                    'epochs': 5,
                    'use_wandb': False
                }
                for i in range(num_jobs)
            ]

        # Launch with concurrency control
        launch_batch_with_concurrency_limit(
            configs,
            mode=mode,
            max_concurrent=max_concurrent,
            check_interval=check_interval,
            region=region
        )

    launch_sweep()


if __name__ == "__main__":
    main()
