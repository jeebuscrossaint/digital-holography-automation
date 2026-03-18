# -*- coding: utf-8 -*-
"""
Main Runner Script for Photonic Lantern Digital Holography Automation

This is the main entry point that runs both data collection and processing.

Usage:
    python run_experiment.py --collect --process    # Run both
    python run_experiment.py --collect              # Collection only
    python run_experiment.py --process              # Processing only
    python run_experiment.py --test                 # Test hardware connections

Author: Amarnath
Date: March 2026
"""

import argparse
import sys
from pathlib import Path

# Ensure we can import our modules
sys.path.append('.')


def test_hardware():
    """Test all hardware connections without collecting data"""
    print("\n" + "=" * 60)
    print("TESTING HARDWARE CONNECTIONS")
    print("=" * 60 + "\n")
    
    from data_collection import HolographyDataCollector
    
    collector = HolographyDataCollector()
    
    try:
        collector.connect_hardware()
        print("\n✓ All hardware tests passed!")
        print("\nHardware is ready for data collection.")
    except Exception as e:
        print(f"\n✗ Hardware test failed: {e}")
        return False
    finally:
        collector.disconnect_hardware()
    
    return True


def run_collection(config_file='experiment_config.yaml'):
    """Run data collection pipeline"""
    print("\n" + "=" * 60)
    print("STARTING DATA COLLECTION")
    print("=" * 60 + "\n")
    
    from data_collection import HolographyDataCollector
    
    collector = HolographyDataCollector(config_file=config_file)
    collector.run()


def run_processing(config_file='experiment_config.yaml', show_plots=False):
    """Run data processing pipeline"""
    print("\n" + "=" * 60)
    print("STARTING DATA PROCESSING")
    print("=" * 60 + "\n")
    
    from data_processing import HolographyDataProcessor
    
    processor = HolographyDataProcessor(config_file=config_file)
    processor.process_dataset(show_plots=show_plots, save_plots=True)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Photonic Lantern Digital Holography Automation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_experiment.py --test                  # Test hardware only
  python run_experiment.py --collect               # Collect data only
  python run_experiment.py --process               # Process existing data
  python run_experiment.py --collect --process     # Full pipeline
  python run_experiment.py --process --show-plots  # Process with live plots
        """
    )
    
    parser.add_argument(
        '--config',
        default='experiment_config.yaml',
        help='Path to configuration YAML file (default: experiment_config.yaml)'
    )
    
    parser.add_argument(
        '--test',
        action='store_true',
        help='Test hardware connections without collecting data'
    )
    
    parser.add_argument(
        '--collect',
        action='store_true',
        help='Run data collection pipeline'
    )
    
    parser.add_argument(
        '--process',
        action='store_true',
        help='Run data processing pipeline'
    )
    
    parser.add_argument(
        '--show-plots',
        action='store_true',
        help='Show plots interactively during processing'
    )
    
    args = parser.parse_args()
    
    # Check that config file exists
    if not Path(args.config).exists():
        print(f"✗ Error: Configuration file not found: {args.config}")
        print(f"Please create a configuration file or specify --config <path>")
        return 1
    
    # If no action specified, show help
    if not (args.test or args.collect or args.process):
        parser.print_help()
        print("\n⚠ No action specified. Use --test, --collect, or --process")
        return 1
    
    try:
        # Test mode
        if args.test:
            success = test_hardware()
            return 0 if success else 1
        
        # Data collection
        if args.collect:
            run_collection(config_file=args.config)
        
        # Data processing
        if args.process:
            run_processing(config_file=args.config, show_plots=args.show_plots)
        
        print("\n" + "=" * 60)
        print("✓ ALL TASKS COMPLETED SUCCESSFULLY")
        print("=" * 60 + "\n")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⚠ Interrupted by user")
        return 130
    
    except Exception as e:
        print(f"\n\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
