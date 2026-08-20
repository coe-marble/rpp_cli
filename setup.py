from setuptools import find_packages, setup


setup(
    name="rpp-cli",
    version="0.1.0",
    description="RPP command line interface",
    packages=find_packages(include=["rpp_cli", "rpp_cli.*"]),
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "rpp=rpp_cli.cli:main",
        ]
    },
    install_requires=[],
)