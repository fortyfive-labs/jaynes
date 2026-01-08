#!/usr/bin/env python3
"""
Launch script for jaynes AWS training

Usage:
    # Run locally
    python launch.py --mode local

    # Run on small GPU (spot instance)
    python launch.py --mode gpu

    # Run on larger GPU
    python launch.py --mode gpu_large

    # Run hyperparameter sweep
    python launch.py --mode gpu --sweep
"""
import jaynes


def single_run():
    """Launch a single training run"""
    from train import train

    jaynes.run(train,
               experiment_name="mnist-demo",
               lr=0.001,
               batch_size=64,
               epochs=10,
               use_wandb=False)


def hyperparameter_sweep():
    """Launch multiple training runs with different hyperparameters"""
    from train import train

    # Grid search over learning rates and batch sizes
    learning_rates = [0.01, 0.001, 0.0001]
    batch_sizes = [32, 64, 128]

    print(f"Launching {len(learning_rates) * len(batch_sizes)} training runs...")

    for lr in learning_rates:
        for bs in batch_sizes:
            jaynes.add(train,
                       experiment_name=f"mnist-sweep-lr{lr}-bs{bs}",
                       lr=lr,
                       batch_size=bs,
                       epochs=5,
                       use_wandb=False)

    # Execute all queued runs
    jaynes.execute()
    print("All runs launched!")


def main():
    from params_proto import proto

    @proto.cli
    def launch(
        mode: str = "local",  # Execution mode: local, debug, gpu, gpu_large, multi_gpu
        sweep: bool = False,  # Run hyperparameter sweep instead of single run
        lr: float = 0.001,  # Learning rate (single run only)
        batch_size: int = 64,  # Batch size (single run only)
        epochs: int = 10,  # Number of epochs (single run only)
    ):
        """Launch MNIST training with jaynes"""
        # Validate mode
        valid_modes = ['local', 'debug', 'gpu', 'gpu_large', 'multi_gpu']
        if mode not in valid_modes:
            raise ValueError(f"mode must be one of {valid_modes}")

        # Configure jaynes
        print(f"Configuring jaynes with mode: {mode}")
        jaynes.config(mode=mode)

        # Launch
        if sweep:
            print("Running hyperparameter sweep...")
            hyperparameter_sweep()
        else:
            print("Running single training job...")
            from train import train
            jaynes.run(train,
                       experiment_name=f"mnist-{mode}",
                       lr=lr,
                       batch_size=batch_size,
                       epochs=epochs)

        # For remote modes, keep the connection alive
        if mode != 'local':
            print("Job launched! Keeping connection alive...")
            jaynes.listen()
            print("Done!")

    launch()


if __name__ == "__main__":
    main()
