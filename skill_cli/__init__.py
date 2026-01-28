"""
DCF Skill CLI

Command-line interface for authoring, validating, and managing DCF skills.

Usage:
    skill <command> [options]

Commands:
    init        Create a new skill from a template
    validate    Validate skill YAML files
    generate    Generate manifests and stub config
    list        List available skills
    test        Run test cases against stub server

Examples:
    skill init research.arxiv
    skill validate
    skill generate
    skill list --format table
    skill test --skill research.web
"""

__version__ = "0.1.0"
