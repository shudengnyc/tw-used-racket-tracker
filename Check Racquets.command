#!/bin/sh
# Double-click this in Finder: asks GitHub to scrape Tennis Warehouse now,
# waits for it, then opens the fresh report.
#
# The scrape itself runs on GitHub -- this machine only fetches the results,
# so there is one copy of the price history and it can't drift.
cd "$(dirname "$0")" || exit 1
# Homebrew's gh isn't on the PATH that Finder hands to .command files.
PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"; export PATH
echo "Asking GitHub for fresh Tennis Warehouse prices..."
python3 tw_used.py --refresh --open "$@" || {
    echo
    echo "Something went wrong. Press any key to close."
    read -r _
    exit 1
}
echo "Done — report opened in your browser."
sleep 1
