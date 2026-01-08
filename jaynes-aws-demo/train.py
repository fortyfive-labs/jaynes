#!/usr/bin/env python3
"""
Simple MNIST training demo for jaynes AWS deployment
"""
import os
import json
import time
from datetime import datetime


def train(
    experiment_name="mnist-demo",
    lr=0.001,
    batch_size=64,
    epochs=5,
    save_model=True,
    use_wandb=False
):
    """
    Train a simple CNN on MNIST dataset

    Args:
        experiment_name: Name for this experiment
        lr: Learning rate
        batch_size: Batch size for training
        epochs: Number of training epochs
        save_model: Whether to save model checkpoint
        use_wandb: Whether to use Weights & Biases logging
    """
    print("=" * 60)
    print(f"Starting training: {experiment_name}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 60)

    # Import here so we fail fast if dependencies missing
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader
    from torchvision import datasets, transforms

    # Check GPU availability
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")
    print()

    # Optional W&B integration
    if use_wandb:
        try:
            import wandb
            wandb.init(
                project=experiment_name,
                config={
                    "lr": lr,
                    "batch_size": batch_size,
                    "epochs": epochs,
                }
            )
            print("✓ Weights & Biases initialized")
        except ImportError:
            print("⚠ wandb not installed, skipping W&B logging")
            use_wandb = False

    # Define simple CNN model
    class SimpleCNN(nn.Module):
        def __init__(self):
            super(SimpleCNN, self).__init__()
            self.conv1 = nn.Conv2d(1, 32, 3, 1)
            self.conv2 = nn.Conv2d(32, 64, 3, 1)
            self.dropout1 = nn.Dropout2d(0.25)
            self.dropout2 = nn.Dropout2d(0.5)
            self.fc1 = nn.Linear(9216, 128)
            self.fc2 = nn.Linear(128, 10)

        def forward(self, x):
            x = self.conv1(x)
            x = nn.functional.relu(x)
            x = self.conv2(x)
            x = nn.functional.relu(x)
            x = nn.functional.max_pool2d(x, 2)
            x = self.dropout1(x)
            x = torch.flatten(x, 1)
            x = self.fc1(x)
            x = nn.functional.relu(x)
            x = self.dropout2(x)
            x = self.fc2(x)
            return nn.functional.log_softmax(x, dim=1)

    # Data loading
    print("Loading MNIST dataset...")
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,))
    ])

    # Download to /tmp to avoid permission issues
    data_dir = os.environ.get('DATA_DIR', '/tmp/mnist_data')
    os.makedirs(data_dir, exist_ok=True)

    train_dataset = datasets.MNIST(
        data_dir, train=True, download=True, transform=transform
    )
    test_dataset = datasets.MNIST(
        data_dir, train=False, download=True, transform=transform
    )

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)
    print(f"✓ Loaded {len(train_dataset)} training samples, {len(test_dataset)} test samples")
    print()

    # Model, optimizer, loss
    model = SimpleCNN().to(device)
    optimizer = optim.Adam(model.parameters(), lr=lr)
    criterion = nn.NLLLoss()

    print(f"Model parameters: {sum(p.numel() for p in model.parameters()):,}")
    print()

    # Create output directory
    output_dir = os.environ.get('OUTPUT_DIR', './outputs')
    os.makedirs(output_dir, exist_ok=True)

    # Training loop
    results = {
        'experiment_name': experiment_name,
        'config': {
            'lr': lr,
            'batch_size': batch_size,
            'epochs': epochs,
        },
        'history': []
    }

    best_accuracy = 0.0

    for epoch in range(1, epochs + 1):
        epoch_start = time.time()

        # Training phase
        model.train()
        train_loss = 0
        correct = 0
        total = 0

        for batch_idx, (data, target) in enumerate(train_loader):
            data, target = data.to(device), target.to(device)

            optimizer.zero_grad()
            output = model(data)
            loss = criterion(output, target)
            loss.backward()
            optimizer.step()

            train_loss += loss.item()
            pred = output.argmax(dim=1, keepdim=True)
            correct += pred.eq(target.view_as(pred)).sum().item()
            total += target.size(0)

            if batch_idx % 100 == 0:
                print(f"Epoch {epoch}/{epochs} [{batch_idx * len(data)}/{len(train_loader.dataset)} "
                      f"({100. * batch_idx / len(train_loader):.0f}%)] Loss: {loss.item():.4f}")

        train_loss /= len(train_loader)
        train_acc = 100. * correct / total

        # Validation phase
        model.eval()
        test_loss = 0
        correct = 0
        total = 0

        with torch.no_grad():
            for data, target in test_loader:
                data, target = data.to(device), target.to(device)
                output = model(data)
                test_loss += criterion(output, target).item()
                pred = output.argmax(dim=1, keepdim=True)
                correct += pred.eq(target.view_as(pred)).sum().item()
                total += target.size(0)

        test_loss /= len(test_loader)
        test_acc = 100. * correct / total

        epoch_time = time.time() - epoch_start

        # Log results
        epoch_results = {
            'epoch': epoch,
            'train_loss': train_loss,
            'train_acc': train_acc,
            'test_loss': test_loss,
            'test_acc': test_acc,
            'time': epoch_time
        }
        results['history'].append(epoch_results)

        print(f"\nEpoch {epoch}/{epochs} Summary:")
        print(f"  Train Loss: {train_loss:.4f}, Train Acc: {train_acc:.2f}%")
        print(f"  Test Loss:  {test_loss:.4f}, Test Acc:  {test_acc:.2f}%")
        print(f"  Time: {epoch_time:.2f}s")
        print()

        if use_wandb:
            wandb.log({
                'epoch': epoch,
                'train_loss': train_loss,
                'train_acc': train_acc,
                'test_loss': test_loss,
                'test_acc': test_acc,
            })

        # Save best model
        if test_acc > best_accuracy:
            best_accuracy = test_acc
            if save_model:
                model_path = os.path.join(output_dir, 'best_model.pth')
                torch.save({
                    'epoch': epoch,
                    'model_state_dict': model.state_dict(),
                    'optimizer_state_dict': optimizer.state_dict(),
                    'test_acc': test_acc,
                    'config': results['config']
                }, model_path)
                print(f"✓ Saved best model (acc: {test_acc:.2f}%) to {model_path}")

    # Save training results
    results['best_accuracy'] = best_accuracy
    results_path = os.path.join(output_dir, 'results.json')
    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2)

    print()
    print("=" * 60)
    print(f"Training completed!")
    print(f"Best test accuracy: {best_accuracy:.2f}%")
    print(f"Results saved to: {output_dir}")
    print("=" * 60)

    if use_wandb:
        wandb.finish()

    return results


if __name__ == "__main__":
    # Simple command-line execution (without jaynes)
    from params_proto import proto

    @proto.cli
    def main(
        experiment_name: str = "mnist-demo",  # Experiment name
        lr: float = 0.001,  # Learning rate
        batch_size: int = 64,  # Batch size
        epochs: int = 5,  # Number of epochs
        use_wandb: bool = False,  # Use Weights & Biases logging
    ):
        """Train MNIST model"""
        train(
            experiment_name=experiment_name,
            lr=lr,
            batch_size=batch_size,
            epochs=epochs,
            use_wandb=use_wandb
        )

    main()
