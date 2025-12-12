# DAZZLE Homebrew Formula (Simplified for Testing)
#
# ⚠️  WARNING: This simplified formula is INCOMPLETE and does NOT work.
# It does not install dependencies correctly because virtualenv_install_with_resources
# uses --no-deps flag by default. Use homebrew/dazzle.rb instead.
#
# This file is kept for reference only.

class DazzleSimple < Formula
  include Language::Python::Virtualenv

  desc "DSL-first application framework with LLM-assisted development"
  homepage "https://github.com/manwithacat/dazzle"

  # For local testing, install from local directory
  url "file:///Volumes/SSD/Dazzle", using: :git, branch: "main"
  version "0.14.0"
  head "https://github.com/manwithacat/dazzle.git", branch: "main"

  depends_on "python@3.12"

  # Core dependencies - using virtualenv_install_with_resources
  # will automatically install dependencies from setup.py/pyproject.toml

  def install
    # Install in virtualenv with all dependencies
    virtualenv_install_with_resources
  end

  def caveats
    <<~EOS
      DAZZLE has been installed!

      Quick start:
        dazzle init my-project
        cd my-project
        dazzle build

      Python location:
        #{opt_libexec}/bin/python

      For VS Code extension, set:
        "dazzle.pythonPath": "#{opt_libexec}/bin/python"

      Documentation:
        https://github.com/manwithacat/dazzle
    EOS
  end

  test do
    # Test that the CLI works
    system "#{bin}/dazzle", "--help"
  end
end
