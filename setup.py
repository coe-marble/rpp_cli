from setuptools import find_packages, setup


setup(
    name="rpp-cli",
    version="0.1.0",
    description="RPP command line interface",
    py_modules=["cli", "commands"],
    packages=find_packages(),
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "rpp=cli:main",
        ]
    },
    install_requires=[],
)