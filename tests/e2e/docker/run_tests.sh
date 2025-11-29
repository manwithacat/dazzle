#!/bin/bash
# Run Dazzle DNR E2E tests using Docker Compose
#
# Usage:
#   ./run_tests.sh                  # Run all tests
#   ./run_tests.sh --build          # Rebuild containers before running
#   ./run_tests.sh --interactive    # Start containers for interactive testing
#   ./run_tests.sh --cleanup        # Stop and remove containers

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.e2e.yaml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Parse arguments
BUILD=""
INTERACTIVE=""
CLEANUP=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --build)
            BUILD="--build"
            shift
            ;;
        --interactive)
            INTERACTIVE="true"
            shift
            ;;
        --cleanup)
            CLEANUP="true"
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# Create screenshots directory
mkdir -p "$SCRIPT_DIR/screenshots"

if [[ "$CLEANUP" == "true" ]]; then
    log_info "Cleaning up containers..."
    docker compose -f "$COMPOSE_FILE" down --remove-orphans
    exit 0
fi

if [[ "$INTERACTIVE" == "true" ]]; then
    log_info "Starting containers for interactive testing..."
    docker compose -f "$COMPOSE_FILE" up $BUILD -d

    log_info "Waiting for services to be healthy..."
    sleep 10

    log_info ""
    log_info "=== Services Running ==="
    log_info "DNR App: http://localhost:8000 (API) / http://localhost:3000 (UI)"
    log_info ""
    log_info "To run tests interactively:"
    log_info "  docker compose -f $COMPOSE_FILE exec playwright pytest /tests/e2e/docker/test_ux_validation.py -v"
    log_info ""
    log_info "To get a shell in the playwright container:"
    log_info "  docker compose -f $COMPOSE_FILE exec playwright bash"
    log_info ""
    log_info "To stop:"
    log_info "  docker compose -f $COMPOSE_FILE down"
    exit 0
fi

# Run tests
log_info "Starting E2E test stack..."

# Build and start services
docker compose -f "$COMPOSE_FILE" up $BUILD -d

log_info "Waiting for services to be healthy..."
sleep 15

# Check if DNR is healthy
if ! docker compose -f "$COMPOSE_FILE" exec -T dnr-app curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    log_error "DNR app is not healthy!"
    docker compose -f "$COMPOSE_FILE" logs dnr-app
    docker compose -f "$COMPOSE_FILE" down
    exit 1
fi

log_info "DNR app is healthy, running tests..."

# Run tests
# Pin playwright version to match Docker image (v1.55.0-noble)
docker compose -f "$COMPOSE_FILE" exec -T playwright \
    pip install pytest httpx 'playwright==1.55.0' > /dev/null 2>&1

TEST_EXIT_CODE=0
docker compose -f "$COMPOSE_FILE" exec -T -w /tests/e2e/docker playwright \
    pytest test_ux_validation.py -v --tb=short || TEST_EXIT_CODE=$?

# Collect screenshots
if [[ -d "$SCRIPT_DIR/screenshots" ]]; then
    log_info "Screenshots saved to: $SCRIPT_DIR/screenshots/"
fi

# Stop services
log_info "Stopping services..."
docker compose -f "$COMPOSE_FILE" down

if [[ $TEST_EXIT_CODE -eq 0 ]]; then
    log_info "All tests passed!"
else
    log_error "Some tests failed (exit code: $TEST_EXIT_CODE)"
fi

exit $TEST_EXIT_CODE
