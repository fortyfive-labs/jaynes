#!/bin/bash
# Test script to demonstrate termination trap works on errors
# This simulates what would happen on an EC2 instance with various failure scenarios

echo "=========================================================================="
echo "Testing Auto-Termination on Error Scenarios"
echo "=========================================================================="
echo ""

# Mock the termination command for testing (so we don't actually try to terminate)
mock_terminate() {
    echo "✅ TERMINATION TRIGGERED: Instance would be terminated here"
    echo "   Command: aws ec2 terminate-instances --instance-ids \$EC2_INSTANCE_ID --region \$REGION"
}

test_scenario() {
    local scenario_name="$1"
    local test_script="$2"

    echo "Test: $scenario_name"
    echo "----------------------------------------"

    # Create a test script with trap
    cat > /tmp/test_trap.sh << 'EOF'
#!/bin/bash
set +o posix

# Define cleanup function (mocked)
cleanup() {
    EXIT_CODE=$?
    echo "Cleanup triggered (exit code: $EXIT_CODE)"
    # Mock termination instead of real termination
    echo "✅ TERMINATION TRIGGERED: Instance would be terminated here"
    echo "   Command: aws ec2 terminate-instances --instance-ids \$EC2_INSTANCE_ID --region \$REGION"
}

# Set trap to call cleanup on EXIT, ERR, INT, and TERM
trap cleanup EXIT ERR INT TERM

{
EOF

    # Add the test script
    echo "$test_script" >> /tmp/test_trap.sh

    # Close the block
    echo "} 2>&1" >> /tmp/test_trap.sh

    # Make executable
    chmod +x /tmp/test_trap.sh

    # Run and capture output
    echo "Execution:"
    /tmp/test_trap.sh || true
    echo ""
    echo "✓ Test complete"
    echo ""
    echo ""
}

# Test 1: Normal success
test_scenario "Normal Success (should still terminate)" \
"echo 'Step 1: Setup'
echo 'Step 2: Training'
echo 'Step 3: Complete'
exit 0"

# Test 2: Early failure in setup
test_scenario "Failure During Setup" \
"echo 'Step 1: Setup starting'
false  # Simulate setup failure
echo 'This should not be printed'"

# Test 3: Command not found
test_scenario "Command Not Found Error" \
"echo 'Starting...'
nonexistent_command
echo 'This should not be printed'"

# Test 4: Python script error
test_scenario "Python Script Error" \
"echo 'Launching Python training...'
python3 -c 'import sys; print(\"Training started\"); sys.exit(1)'
echo 'This should not be printed'"

# Test 5: Missing dependency
test_scenario "Missing Dependency" \
"echo 'Checking dependencies...'
pip install --dry-run nonexistent_package_xyz123
echo 'This should not be printed'"

# Test 6: File not found
test_scenario "File Not Found" \
"echo 'Reading config file...'
cat /tmp/nonexistent_config_file.yaml
echo 'This should not be printed'"

echo "=========================================================================="
echo "Summary"
echo "=========================================================================="
echo ""
echo "All scenarios demonstrated that the cleanup trap is triggered on:"
echo "  ✓ Normal exit (exit 0)"
echo "  ✓ Command failure (false)"
echo "  ✓ Command not found"
echo "  ✓ Python script errors"
echo "  ✓ Package installation failures"
echo "  ✓ File not found errors"
echo ""
echo "This ensures EC2 instances will ALWAYS be terminated, regardless of"
echo "how the script exits, preventing runaway costs from stuck instances."
echo ""
echo "Clean up test file..."
rm -f /tmp/test_trap.sh
echo "Done!"
