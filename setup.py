from setuptools import setup, find_packages

setup(
    name="polymarket_bot",
    version="0.0.0",
    description="Polymarket bot MVP scaffold",
    packages=find_packages(exclude=("tests",)),
    python_requires=">=3.11",
)
