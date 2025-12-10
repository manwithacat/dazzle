# DAZZLE Homebrew Formula v0.8.0
#
# Installation: brew install manwithacat/tap/dazzle
# Or from this file: brew install ./homebrew/dazzle.rb
#
# v0.8.0 Architecture:
# - CLI: Bun-compiled native binary (50x faster startup)
# - Runtime: Python package for DSL parsing and code generation
#
# The binary is built from cli/ using `bun build --compile`
# Python is invoked only when DSL operations are needed

class Dazzle < Formula
  include Language::Python::Virtualenv

  desc "DSL-first application framework with LLM-assisted development"
  homepage "https://github.com/manwithacat/dazzle"
  version "0.8.0"
  license "MIT"

  # Source tarball for Python package
  url "https://github.com/manwithacat/dazzle/archive/refs/tags/v0.8.0.tar.gz"
  sha256 "b0cfcbe8ec1943a8b04df3c7bf6cab8e2f3152112c9c3145eded0d054701cb89"

  # Pre-compiled CLI binaries for each platform
  resource "cli-binary" do
    on_macos do
      on_arm do
        url "https://github.com/manwithacat/dazzle/releases/download/v0.8.0/dazzle-darwin-arm64.tar.gz"
        sha256 "1c39cccf60b7089db2b596ef064dcc2be02e9162ab0a32fddb874ce17460047f"
      end
      on_intel do
        url "https://github.com/manwithacat/dazzle/releases/download/v0.8.0/dazzle-darwin-x64.tar.gz"
        sha256 "83bb943aa35bbdb66f4576155e3a7afb7aafff4dab8a4912cddc6ed229788978"
      end
    end
    on_linux do
      on_arm do
        url "https://github.com/manwithacat/dazzle/releases/download/v0.8.0/dazzle-linux-arm64.tar.gz"
        sha256 "e53546ae7c35bf0432f38efd87008c3302e72f12157b75b7bfef20bf018c18bb"
      end
      on_intel do
        url "https://github.com/manwithacat/dazzle/releases/download/v0.8.0/dazzle-linux-x64.tar.gz"
        sha256 "58c21aac08ac3026d58896ef867c1d93c5fee521a5e560525feef83b2f1b59a5"
      end
    end
  end

  depends_on "python@3.12"

  # Python dependencies for DSL parsing and runtime
  resource "pydantic" do
    url "https://files.pythonhosted.org/packages/source/p/pydantic/pydantic-2.9.2.tar.gz"
    sha256 "d155cef71265d1e9807ed1c32b4c8deec042a44a50a4188b25ac67ecd81a9c0f"
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

  resource "typing-extensions" do
    url "https://files.pythonhosted.org/packages/source/t/typing-extensions/typing_extensions-4.12.2.tar.gz"
    sha256 "1a7ead55c7e559dd4dee8856e3a88b41225abfe1ce8df57b7c13915fe121ffb8"
  end

  resource "annotated-types" do
    url "https://files.pythonhosted.org/packages/source/a/annotated-types/annotated_types-0.7.0.tar.gz"
    sha256 "aff07c09a53a08bc8cfccb9c85b05f1aa9a2a6f23728d790723543408344ce89"
  end

  resource "typer" do
    url "https://files.pythonhosted.org/packages/source/t/typer/typer-0.12.5.tar.gz"
    sha256 "f592f089bedcc8ec1b974125d64851029c3b1af145f04aca64d69410f0c9b722"
  end

  resource "click" do
    url "https://files.pythonhosted.org/packages/source/c/click/click-8.1.7.tar.gz"
    sha256 "ca9853ad459e787e2192211578cc907e7594e294c7ccc834310722b41b9ca6de"
  end

  resource "rich" do
    url "https://files.pythonhosted.org/packages/source/r/rich/rich-13.9.2.tar.gz"
    sha256 "51a2c62057461aaf7152b4d611168f93a9fc73068f8ded2790f29fe2b5366d0c"
  end

  resource "jinja2" do
    url "https://files.pythonhosted.org/packages/df/bf/f7da0350254c0ed7c72f3e33cef02e048281fec7ecec5f032d4aac52226b/jinja2-3.1.6.tar.gz"
    sha256 "0137fb05990d35f1275a587e9aee6d56da821fc83491a0fb838183be43f66d6d"
  end

  resource "markupsafe" do
    url "https://files.pythonhosted.org/packages/7e/99/7690b6d4034fffd95959cbe0c02de8deb3098cc577c67bb6a24fe5d7caa7/markupsafe-3.0.3.tar.gz"
    sha256 "722695808f4b6457b320fdc131280796bdceb04ab50fe1795cd540799ebe1698"
  end

  resource "pyyaml" do
    url "https://files.pythonhosted.org/packages/54/ed/79a089b6be93607fa5cdaedf301d7dfb23af5f25c398d5ead2525b063e17/pyyaml-6.0.2.tar.gz"
    sha256 "d584d9ec91ad65861cc08d42e834324ef890a082e591037abe114850ff7bbc3e"
  end

  def install
    # Install Python package in virtualenv
    venv = virtualenv_create(libexec, "python3.12")

    # Install Python dependencies
    resources.each do |r|
      next if r.name == "cli-binary"

      case r.name
      when "pydantic-core"
        # pydantic-core is distributed as a wheel (requires Rust to build from source)
        r.stage do
          wheel = Dir["*.whl"].first
          odie "pydantic-core wheel not found in resource" unless wheel

          system venv.root/"bin/python", "-m", "pip", "install",
                 "--no-deps", "--no-compile",
                 wheel
        end
      else
        venv.pip_install r
      end
    end

    # Install dazzle package (don't link - we provide our own CLI binary)
    venv.pip_install buildpath

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
      DAZZLE v0.8.0 has been installed!

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

      For LLM features:
        #{libexec}/bin/pip install anthropic openai

      Documentation:
        https://github.com/manwithacat/dazzle
    EOS
  end

  test do
    # Test fast path (no Python needed)
    output = shell_output("#{bin}/dazzle version")
    assert_match "0.8.0", output

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
