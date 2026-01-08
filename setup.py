from os import path

from setuptools import setup, find_packages

# Use a simple description instead of the full README to avoid RST parsing issues
long_description = """
Jaynes - A Utility for training ML models on AWS, GCE, SLURM

A tool for running Python ML training code on heterogeneous infrastructure including
AWS EC2, Google Cloud, SLURM clusters, and local machines. Makes distributed training
across different hardware resources simple and consistent.

For more information and documentation, visit: https://github.com/episodeyang/jaynes
"""
with open(path.join(path.abspath(path.dirname(__file__)), 'VERSION'), encoding='utf-8') as f:
    version = f.read()
with open(path.join(path.abspath(path.dirname(__file__)), 'LICENSE'), encoding='utf-8') as f:
    license = f.read()

setup(
    name="jaynes",
    description="A tool for running python code with runner on aws",
    long_description=long_description,
    long_description_content_type='text/plain',
    version=version,
    url="https://github.com/episodeyang/jaynes",
    author="Ge Yang",
    author_email="yangge1987@gmail.com",
    license=license,
    keywords=["jaynes", "logging", "DEBUG", "debugging", "timer",
              "timeit", "decorator", "stopwatch", "tic", "toc",
              ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Programming Language :: Python :: 3"
    ],
    packages=find_packages(),
    install_requires=[
        "aiofile",
        "cloudpickle==3.1.1",
        "functional_notations",
        "pyyaml",
        "requests",
        "termcolor",
    ]
)
