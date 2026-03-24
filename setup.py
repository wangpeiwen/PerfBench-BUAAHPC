from setuptools import setup, find_packages

setup(
    name="perfbench",
    version="1.0.0",
    description="PerfBench - 超算集群性能基准测试工具",
    author="PerfBench Team",
    packages=find_packages(),
    python_requires=">=3.6",
    install_requires=[
        "questionary>=1.10.0",
        "reportlab>=3.6.0",   # PDF 覆盖层生成（certificate_generator.py）
        "pypdf>=3.0.0",       # PDF 模板读取与合并（certificate_generator.py）
    ],
    entry_points={
        'console_scripts': [
            'perfbench=perfbench.__main__:main',
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
    ],
)