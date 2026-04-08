#!/usr/bin/env python3
"""
Convert large Excel files to Parquet for fast loading.

150MB Excel files are too large for GitHub and slow to load.
This script converts them to Parquet format which is:
- 5-10x smaller than Excel
- 10-50x faster to load
- Supports column-level reading (only load what you need)

Usage (run in PowerShell or Terminal):

    pip install -r requirements.txt
    python scripts/convert_to_parquet.py --w33 "path/to/full_w33_data.xlsx"
    python scripts/convert_to_parquet.py --longitudinal "path/to/full_longitudinal_data.xlsx"
    python scripts/convert_to_parquet.py --both "path/to/w33.xlsx" "path/to/longitudinal.xlsx"

The converted files are saved in the data/ folder and are used
automatically by the dashboard.
"""

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

try:
    import pyarrow  # noqa: F401
except ImportError:
    print("Installing pyarrow (needed for Parquet format)...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyarrow"])

import pandas as pd


def convert_excel_to_parquet(
    excel_path: str,
    output_path: str,
    sheet_name: str = 0,
    description: str = "",
):
    """Convert an Excel file to Parquet format."""
    excel_path = Path(excel_path)
    output_path = Path(output_path)

    if not excel_path.exists():
        print(f"ERROR: File not found: {excel_path}")
        sys.exit(1)

    excel_size_mb = excel_path.stat().st_size / (1024 * 1024)
    print(f"\nConverting: {excel_path.name}")
    print(f"  Excel size: {excel_size_mb:.1f} MB")
    if description:
        print(f"  Description: {description}")
    print(f"  Reading Excel... (this may take a minute for large files)")

    df = pd.read_excel(excel_path, sheet_name=sheet_name)
    print(f"  Shape: {df.shape[0]:,} rows x {df.shape[1]:,} columns")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False, engine="pyarrow")

    parquet_size_mb = output_path.stat().st_size / (1024 * 1024)
    ratio = excel_size_mb / parquet_size_mb if parquet_size_mb > 0 else 0
    print(f"  Parquet size: {parquet_size_mb:.1f} MB ({ratio:.1f}x compression)")
    print(f"  Saved to: {output_path}")

    return df


def main():
    parser = argparse.ArgumentParser(
        description="Convert large Excel files to fast Parquet format"
    )
    parser.add_argument(
        "--w33",
        type=str,
        help="Path to the full W33 Excel file",
    )
    parser.add_argument(
        "--longitudinal",
        type=str,
        help="Path to the full longitudinal Excel file",
    )
    parser.add_argument(
        "--both",
        nargs=2,
        metavar=("W33_PATH", "LONGITUDINAL_PATH"),
        help="Paths to both files",
    )
    args = parser.parse_args()

    data_dir = project_root / "data"
    data_dir.mkdir(exist_ok=True)

    if args.both:
        args.w33 = args.both[0]
        args.longitudinal = args.both[1]

    if not args.w33 and not args.longitudinal:
        parser.print_help()
        print("\n\nExample usage:")
        print('  python scripts/convert_to_parquet.py --w33 "C:\\Users\\you\\Downloads\\W33_full.xlsx"')
        print('  python scripts/convert_to_parquet.py --longitudinal "C:\\Users\\you\\Downloads\\Longitudinal_full.xlsx"')
        sys.exit(0)

    if args.w33:
        convert_excel_to_parquet(
            args.w33,
            data_dir / "w33_full.parquet",
            sheet_name="A1",
            description="Full W33 respondent-level data",
        )

    if args.longitudinal:
        convert_excel_to_parquet(
            args.longitudinal,
            data_dir / "longitudinal_full.parquet",
            description="Full historical longitudinal data (all waves)",
        )

    print(f"\n{'='*60}")
    print("DONE! The dashboard will now use the converted files.")
    print(f"Files saved in: {data_dir}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
