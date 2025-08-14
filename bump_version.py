def increment_version(version):
    # Split the version string into major, minor, and patch parts
    major, minor, patch = map(int, version.split("."))

    # Increment the patch
    patch += 1

    # Check if the patch needs to roll over
    if patch == 100:
        patch = 0
        minor += 1

    # Check if the minor needs to roll over
    if minor == 100:
        minor = 0
        major += 1

    # Format the new version string
    return f"{major}.{minor}.{patch}"


# Read the current version from the file
with open("version.txt", "r") as f:
    new_version = increment_version(f.read().strip())

# Write the new version back to the file
with open("version.txt", "w") as f:
    f.write(new_version)

print(f"Updated version: {new_version}")
