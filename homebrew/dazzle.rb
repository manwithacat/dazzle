# DAZZLE Homebrew Formula v0.8.11
#
# Installation: brew install manwithacat/tap/dazzle
# Or from this file: brew install ./homebrew/dazzle.rb
#
# v0.8.6 Architecture:
# - CLI: Bun-compiled native binary (50x faster startup)
# - Runtime: Python package for DSL parsing and code generation
#
# The binary is built from cli/ using `bun build --compile`
# Python is invoked only when DSL operations are needed

class Dazzle < Formula
  include Language::Python::Virtualenv

  desc "DSL-first application framework with LLM-assisted development"
  homepage "https://github.com/manwithacat/dazzle"
  version "0.8.11"
  license "MIT"

  # Source tarball for Python package
  url "https://github.com/manwithacat/dazzle/archive/refs/tags/v0.8.11.tar.gz"
  sha256 "PLACEHOLDER_SHA256_SOURCE"

  # Pre-compiled CLI binaries for each platform
  resource "cli-binary" do
    on_macos do
      on_arm do
        url "https://github.com/manwithacat/dazzle/releases/download/v0.8.11/dazzle-darwin-arm64.tar.gz"
        sha256 "PLACEHOLDER_SHA256_DARWIN_ARM64"
      end
      on_intel do
        url "https://github.com/manwithacat/dazzle/releases/download/v0.8.11/dazzle-darwin-x64.tar.gz"
        sha256 "PLACEHOLDER_SHA256_DARWIN_X64"
      end
    end
    on_linux do
      on_arm do
        url "https://github.com/manwithacat/dazzle/releases/download/v0.8.11/dazzle-linux-arm64.tar.gz"
        sha256 "PLACEHOLDER_SHA256_LINUX_ARM64"
      end
      on_intel do
        url "https://github.com/manwithacat/dazzle/releases/download/v0.8.11/dazzle-linux-x64.tar.gz"
        sha256 "PLACEHOLDER_SHA256_LINUX_X64"
      end
    end
  end

  # pydantic-core requires Rust to build from source, so use pre-built wheels
  resource "pydantic-core" do
    on_macos do
      on_arm do
        url "https://files.pythonhosted.org/packages/14/de/866bdce10ed808323d437612aca1ec9971b981e1c52e5e42ad9b8e17a6f6/pydantic_core-2.23.4-cp312-cp312-macosx_11_0_arm64.whl"
        sha256 "f69a8e0b033b747bb3e36a44e7732f0c99f7edd5cea723d45bc0d6e95377ffee"
      end
      on_intel do
        url "https://files.pythonhosted.org/packages/74/7b/8e315f80666194b354966ec84b7d567da77ad927ed6323db4006cf915f3f/pydantic_core-2.23.4-cp312-cp312-macosx_10_12_x86_64.whl"
        sha256 "f3e0da4ebaef65158d4dfd7d3678aad692f7666877df0002b8a522cdf088f231"
      end
    end
    on_linux do
      on_arm do
        url "https://files.pythonhosted.org/packages/dc/69/8edd5c3cd48bb833a3f7ef9b81d7666ccddd3c9a635225214e044b6e8281/pydantic_core-2.23.4-cp312-cp312-manylinux_2_17_aarch64.manylinux2014_aarch64.whl"
        sha256 "723314c1d51722ab28bfcd5240d858512ffd3116449c557a1336cbe3919beb87"
      end
      on_intel do
        url "https://files.pythonhosted.org/packages/06/c8/7d4b708f8d05a5cbfda3243aad468052c6e99de7d0937c9146c24d9f12e9/pydantic_core-2.23.4-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
        sha256 "128585782e5bfa515c590ccee4b727fb76925dd04a98864182b22e89a4e6ed36"
      end
    end
  end

  depends_on "python@3.12"

  # Skip dylib relocation for jiter - its header is too small for Homebrew's
  # install_name_tool modifications. This is safe because jiter is only used
  # at runtime within the virtualenv, not linked by other formulae.
  skip_clean "libexec/lib/python3.12/site-packages/jiter"

  def install
    # Install Python package in virtualenv
    venv = virtualenv_create(libexec, "python3.12")

    # Install pydantic-core wheel first (requires Rust to build from source)
    resource("pydantic-core").stage do
      wheel = Dir["*.whl"].first
      odie "pydantic-core wheel not found in resource" unless wheel

      system venv.root/"bin/python", "-m", "pip", "install",
             "--no-deps", "--no-compile",
             wheel
    end

    # Install dazzle with all optional dependencies (mcp, llm, lsp)
    # pip will resolve transitive dependencies and use our pre-installed pydantic-core
    system venv.root/"bin/python", "-m", "pip", "install",
           "--no-compile",
           "#{buildpath}[mcp,llm,lsp]"

    # Install the pre-compiled CLI binary
    resource("cli-binary").stage do
      bin.install "dazzle" => "dazzle-bin"
    end

    # Create wrapper script that sets up Python path
    (bin/"dazzle").write <<~EOS
      #!/bin/bash
      export DAZZLE_PYTHON="#{libexec}/bin/python"
      export PYTHONPATH="#{libexec}/lib/python3.12/site-packages:$PYTHONPATH"
      exec "#{bin}/dazzle-bin" "$@"
    EOS
    chmod 0755, bin/"dazzle"
  end

  def post_install
    # Register MCP server with Claude Code
    system libexec/"bin/python", "-m", "dazzle.cli", "mcp-setup"
  rescue StandardError => e
    opoo "Could not register MCP server: #{e.message}"
    opoo "You can manually register later with: dazzle mcp-setup"
  end

  def caveats
    <<~EOS
      DAZZLE v0.8.11 has been installed!

      What's New:
        - 50x faster CLI startup (Bun-compiled binary)
        - LLM-friendly JSON output (pipe to agents)
        - Simplified command structure

      Quick start:
        dazzle new my-project
        cd my-project
        dazzle dev

      Commands:
        dazzle new      Create a new project
        dazzle dev      Start development server (API + UI)
        dazzle check    Validate DSL files
        dazzle build    Build for production
        dazzle eject    Generate standalone code
        dazzle test     Run E2E tests

      JSON output (for AI agents):
        dazzle check --json
        dazzle show entities --json

      MCP Server (Claude Code):
        The DAZZLE MCP server has been automatically registered.
        Check status: dazzle mcp-check

      Documentation:
        https://github.com/manwithacat/dazzle
    EOS
  end

  test do
    # Test fast path (no Python needed)
    output = shell_output("#{bin}/dazzle version")
    assert_match "0.8.11", output

    # Test Python integration
    output = shell_output("#{bin}/dazzle version --full")
    assert_match "python_available", output

    # Test basic functionality
    (testpath/"dazzle.toml").write <<~TOML
      [project]
      name = "test"
      version = "0.1.0"
    TOML

    (testpath/"dsl").mkpath
    (testpath/"dsl/app.dsl").write <<~DSL
      module test
      app test "Test App"

      entity Task "Task":
        id: uuid pk
        title: str(200) required
    DSL

    # Test validation
    output = shell_output("#{bin}/dazzle check --json")
    assert_match '"success"', output
  end
end
