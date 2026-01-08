#!/usr/bin/env python3
"""
Test script to verify that the termination trap works correctly
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jaynes.launchers.base_launcher import make_launch_script
from jaynes.runners import Runner


def test_termination_trap_ec2():
    """Test that EC2 termination trap is properly generated"""

    # Create a simple runner
    runner = Runner(
        mounts=[],
        work_dir="/tmp/test",
    )
    runner.setup_script = "echo 'Setup'"
    runner.run_script = "echo 'Running'"
    runner.post_script = "echo 'Post'"

    script = make_launch_script(
        runners=(runner,),
        mounts=[],
        unpack_on_host=False,
        type="ec2",
        launch_dir="/tmp/test",
        terminate_after=True,
        delay=5,
        instance_name="test-instance"
    )

    print("=" * 80)
    print("Generated EC2 Launch Script with Termination Trap:")
    print("=" * 80)
    print(script)
    print("=" * 80)

    # Verify the script contains the trap
    assert "trap cleanup EXIT ERR INT TERM" in script, "Missing trap command"
    assert "cleanup()" in script, "Missing cleanup function"
    assert "terminate-instances" in script, "Missing EC2 termination command"
    assert "Cleanup triggered" in script, "Missing cleanup message"

    print("\n✅ EC2 termination trap test PASSED")
    print("   - Trap function defined")
    print("   - Trap set for EXIT, ERR, INT, TERM signals")
    print("   - Termination commands included in cleanup")


def test_termination_trap_gce():
    """Test that GCE termination trap is properly generated"""

    # Create a simple runner
    runner = Runner(
        mounts=[],
        work_dir="/tmp/test",
    )
    runner.setup_script = "echo 'Setup'"
    runner.run_script = "echo 'Running'"

    script = make_launch_script(
        runners=(runner,),
        mounts=[],
        unpack_on_host=False,
        type="gce",
        launch_dir="/tmp/test",
        terminate_after=True,
        delay=10,
    )

    print("\n" + "=" * 80)
    print("Generated GCE Launch Script with Termination Trap:")
    print("=" * 80)
    print(script)
    print("=" * 80)

    # Verify the script contains the trap
    assert "trap cleanup EXIT ERR INT TERM" in script, "Missing trap command"
    assert "cleanup()" in script, "Missing cleanup function"
    assert "gcloud --quiet compute instances delete" in script, "Missing GCE termination command"

    print("\n✅ GCE termination trap test PASSED")
    print("   - Trap function defined")
    print("   - Trap set for EXIT, ERR, INT, TERM signals")
    print("   - Termination commands included in cleanup")


def test_no_termination_trap():
    """Test that no trap is added when terminate_after=False"""

    runner = Runner(
        mounts=[],
        work_dir="/tmp/test",
    )
    runner.setup_script = "echo 'Setup'"
    runner.run_script = "echo 'Running'"

    script = make_launch_script(
        runners=(runner,),
        mounts=[],
        unpack_on_host=False,
        type="ec2",
        launch_dir="/tmp/test",
        terminate_after=False,
    )

    print("\n" + "=" * 80)
    print("Generated Script WITHOUT Termination (terminate_after=False):")
    print("=" * 80)
    print(script)
    print("=" * 80)

    # Verify no trap is added
    assert "trap cleanup" not in script, "Unexpected trap command when terminate_after=False"
    assert "cleanup()" not in script, "Unexpected cleanup function when terminate_after=False"

    print("\n✅ No termination trap test PASSED")
    print("   - No trap added when terminate_after=False")


if __name__ == "__main__":
    test_termination_trap_ec2()
    test_termination_trap_gce()
    test_no_termination_trap()

    print("\n" + "=" * 80)
    print("🎉 ALL TESTS PASSED!")
    print("=" * 80)
    print("\nThe termination trap ensures instances will be terminated on:")
    print("  • Normal exit (EXIT)")
    print("  • Errors (ERR)")
    print("  • Interrupt signals (INT - Ctrl+C)")
    print("  • Termination signals (TERM - kill)")
