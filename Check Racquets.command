#!/bin/sh
# Double-click this in Finder: scrapes Tennis Warehouse, rebuilds report.html,
# and opens it in your default browser.
cd "$(dirname "$0")" || exit 1
echo "Checking Tennis Warehouse for used racquets..."
python3 tw_used.py --open "$@" || {
    echo
    echo "Something went wrong. Press any key to close."
    read -r _
    exit 1
}
echo "Done — report opened in your browser."
sleep 1
