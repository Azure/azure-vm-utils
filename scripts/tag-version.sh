#!/bin/bash
set -e

VERSION_FILE="src/version.h"

if [ ! -f "$VERSION_FILE" ]; then
    echo "Failed to find version file: $VERSION_FILE"
    exit 1
fi

CURRENT_VERSION=$(cat "$VERSION_FILE" | sed 's|#define VERSION ||' | sed 's|"||g' )
echo "Current version: $CURRENT_VERSION"

IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"

if [ "$1" == "major" ]; then
    let MAJOR+=1
    MINOR=0
    PATCH=0
elif [ "$1" == "minor" ]; then
    let MINOR+=1
    PATCH=0
elif [ "$1" == "patch" ]; then
    let PATCH+=1
else
    echo "Invalid version type specified. Use 'major', 'minor', or 'patch'."
    exit 2
fi

NEW_VERSION="$MAJOR.$MINOR.$PATCH"
echo "New version: $NEW_VERSION"
echo "#define VERSION \"$NEW_VERSION\"" > "$VERSION_FILE"

git add "$VERSION_FILE"
git commit -m "Bump version to $NEW_VERSION"
git tag -a "v$NEW_VERSION" -m "Release version $NEW_VERSION"

echo "Version updated and tagged successfully."
