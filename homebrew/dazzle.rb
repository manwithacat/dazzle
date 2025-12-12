# DAZZLE Homebrew Formula v0.14.0
#
# Installation: brew install manwithacat/tap/dazzle
# Or from this file: brew install ./homebrew/dazzle.rb
#
# v0.14.0 Architecture:
# - CLI: Bun-compiled native binary (50x faster startup)
# - Runtime: Python package for DSL parsing and code generation
#
# The binary is built from cli/ using `bun build --compile`
# Python is invoked only when DSL operations are needed

class Dazzle < Formula
  include Language::Python::Virtualenv

  desc "DSL-first application framework with LLM-assisted development"
  homepage "https://github.com/manwithacat/dazzle"
  version "0.14.0"
  license "MIT"

  # Source tarball for Python package
  # SHA256 will be updated by CI after tag is created
  url "https://github.com/manwithacat/dazzle/archive/refs/tags/v0.14.0.tar.gz"
  sha256 "PLACEHOLDER_SOURCE_SHA256"

  # Pre-compiled CLI binaries for each platform
  # SHA256 values will be updated by CI after release binaries are built
  resource "cli-binary" do
    on_macos do
      on_arm do
        url "https://github.com/manwithacat/dazzle/releases/download/v0.14.0/dazzle-darwin-arm64.tar.gz"
        sha256 "PLACEHOLDER_DARWIN_ARM64_SHA256"
      end
      on_intel do
        url "https://github.com/manwithacat/dazzle/releases/download/v0.14.0/dazzle-darwin-x64.tar.gz"
        sha256 "PLACEHOLDER_DARWIN_X64_SHA256"
      end
    end
    on_linux do
      on_arm do
        url "https://github.com/manwithacat/dazzle/releases/download/v0.14.0/dazzle-linux-arm64.tar.gz"
        sha256 "PLACEHOLDER_LINUX_ARM64_SHA256"
      end
      on_intel do
        url "https://github.com/manwithacat/dazzle/releases/download/v0.14.0/dazzle-linux-x64.tar.gz"
        sha256 "PLACEHOLDER_LINUX_X64_SHA256"
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

  # jiter also requires Rust to build - pre-built wheels avoid dylib header issues
  # The jiter dylib has minimal Mach-O headers that cause install_name_tool failures
  resource "jiter" do
    on_macos do
      on_arm do
        url "https://files.pythonhosted.org/packages/98/6e/e8efa0e78de00db0aee82c0cf9e8b3f2027efd7f8a71f859d8f4be8e98ef/jiter-0.12.0-cp312-cp312-macosx_11_0_arm64.whl"
        sha256 "5c1860627048e302a528333c9307c818c547f214d8659b0705d2195e1a94b274"
      end
      on_intel do
        url "https://files.pythonhosted.org/packages/92/c9/5b9f7b4983f1b542c64e84165075335e8a236fa9e2ea03a0c79780062be8/jiter-0.12.0-cp312-cp312-macosx_10_12_x86_64.whl"
        sha256 "305e061fa82f4680607a775b2e8e0bcb071cd2205ac38e6ef48c8dd5ebe1cf37"
      end
    end
    on_linux do
      on_arm do
        url "https://files.pythonhosted.org/packages/20/26/894cd88e60b5d58af53bec5c6759d1292bd0b37a8b5f60f07abf7a63ae5f/jiter-0.12.0-cp312-cp312-manylinux_2_17_aarch64.manylinux2014_aarch64.whl"
        sha256 "df37577a4f8408f7e0ec3205d2a8f87672af8f17008358063a4d6425b6081ce3"
      end
      on_intel do
        url "https://files.pythonhosted.org/packages/71/b3/7a69d77943cc837d30165643db753471aff5df39692d598da880a6e51c24/jiter-0.12.0-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
        sha256 "4321e8a3d868919bcb1abb1db550d41f2b5b326f72df29e53b2df8b006eb9403"
      end
    end
  end

  depends_on "python@3.12"

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

    # Install jiter wheel (dylib has minimal Mach-O headers that break install_name_tool)
    resource("jiter").stage do
      wheel = Dir["*.whl"].first
      odie "jiter wheel not found in resource" unless wheel

      system venv.root/"bin/python", "-m", "pip", "install",
             "--no-deps", "--no-compile",
             wheel
    end

    # Install dazzle with all optional dependencies (mcp, llm, lsp)
    # pip will resolve transitive dependencies and use our pre-installed pydantic-core and jiter
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
      DAZZLE v0.14.0 has been installed!

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
    assert_match "0.14.0", output

    # Test Python integration
    output = shell_output("#{bin}/dazzle version --full")
    assert_match "python_available", output

    # Test LSP dependencies are installed (critical for VS Code extension)
    # This catches the regression where [lsp] extras were missing from pip install
    system libexec/"bin/python", "-c", "import dazzle.lsp"

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
