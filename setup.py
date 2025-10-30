from setuptools import setup, find_packages

setup(
    name="perfbench",
    version="1.0.0",
    description="SLURM集群性能基准测试工具",
    author="PerfBench Team",
    packages=find_packages(),
    python_requires=">=3.6",
    entry_points={
        'console_scripts': [
            'perfbench=perfbench.main:main',
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
    ],
)