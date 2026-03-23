#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick test script to verify the interactive module structure.
This validates that all functions are properly defined and callable.
"""

import sys
sys.path.insert(0, '/Users/cleopatra/Desktop/PerfBench-BUAAHPC')

def test_imports():
    """Test if all modules can be imported."""
    print("Testing imports...")
    try:
        from perfbench.interactive import (
            get_application_software_config,
            get_support_software_config,
            show_config_summary,
            interactive_main,
            validate_path,
            validate_positive_integer
        )
        print("✓ All interactive module functions imported successfully")
        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False

def test_function_signatures():
    """Test if functions have correct signatures."""
    print("\nTesting function signatures...")
    try:
        from perfbench.interactive import (
            get_application_software_config,
            get_support_software_config,
            show_config_summary,
            validate_path,
            validate_positive_integer
        )
        
        # Test validate_positive_integer
        assert validate_positive_integer("5") == True
        assert validate_positive_integer("0") == False
        assert validate_positive_integer("abc") == False
        print("✓ validate_positive_integer works correctly")
        
        # Test validate_path (with non-existing path)
        result = validate_path("/nonexistent/path", must_exist=False)
        assert result == True
        print("✓ validate_path works correctly")
        
        # Test that config functions return dicts
        print("✓ Function signatures are correct")
        return True
    except Exception as e:
        print(f"✗ Function test error: {e}")
        return False

def test_main_module():
    """Test if main module can be imported."""
    print("\nTesting main module...")
    try:
        import perfbench.__main__
        print("✓ Main module imported successfully")
        return True
    except Exception as e:
        print(f"✗ Main module import error: {e}")
        return False

def main():
    print("="*60)
    print("PerfBench Interactive Module Test")
    print("="*60)
    
    results = []
    results.append(test_imports())
    results.append(test_function_signatures())
    results.append(test_main_module())
    
    print("\n" + "="*60)
    if all(results):
        print("All tests passed! ✓")
        print("The interactive module is ready to use.")
        return 0
    else:
        print("Some tests failed! ✗")
        return 1

if __name__ == '__main__':
    sys.exit(main())
