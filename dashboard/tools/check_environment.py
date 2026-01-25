
if __name__ == "__main__":
    import os
    import sys

    required_packages = [
        "streamlit",
        "pandas",
        "numpy",
        "matplotlib",
        "seaborn",
        "plotly",
        "requests",
        "configparser",
    ]

    missing_packages = []
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)

    if missing_packages:
        print("The following required packages are missing:")
        for pkg in missing_packages:
            print(f"- {pkg}")
        print("\nPlease install them using pip or conda.")
        sys.exit(1)
    else:
        print("All required packages are installed.")

    # Show installed packages using pip in a pretty (column) format.
    # Use the current Python interpreter's pip to ensure consistency.
    try:
        import subprocess

        cmd = [sys.executable, "-m", "pip", "list", "--format=columns"]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            print("\nInstalled packages (pip list):")
            print(proc.stdout.strip())
        else:
            # Fallback to a simple importlib.metadata listing if pip failed
            print("\nFailed to run 'pip list' (stderr below); falling back to package metadata:\n")
            if proc.stderr:
                print(proc.stderr.strip())
            try:
                # Python 3.8+: importlib.metadata
                try:
                    from importlib.metadata import distributions
                except Exception:
                    # For older Python versions, try pkg_resources
                    distributions = None
                if distributions:
                    rows = []
                    for d in distributions():
                        rows.append((d.metadata['Name'], d.version))
                    # simple column output
                    name_w = max((len(r[0]) for r in rows), default=4)
                    ver_w = max((len(r[1]) for r in rows), default=7)
                    print(f"{'Package'.ljust(name_w)}  {'Version'.ljust(ver_w)}")
                    print("-" * (name_w + ver_w + 2))
                    for n, v in sorted(rows):
                        print(f"{n.ljust(name_w)}  {v.ljust(ver_w)}")
            except Exception:
                pass
    except Exception as e:
        print(f"Failed to enumerate installed packages: {e}")