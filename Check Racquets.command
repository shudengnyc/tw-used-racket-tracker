#!/bin/sh
# Double-click this in Finder: scrapes Tennis Warehouse from this Mac (a few
# seconds), opens the report, then quietly pushes the results to GitHub so the
# published page and the price history stay in step.
cd "$(dirname "$0")" || exit 1
# Homebrew's git/gh aren't on the PATH that Finder hands to .command files.
PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"; export PATH
echo "Checking Tennis Warehouse for used racquets..."
python3 tw_used.py --open "$@" || {
    echo
    echo "Something went wrong. Press any key to close."
    read -r _
    exit 1
}
echo "Done — report opened in your browser."
sleep 1
