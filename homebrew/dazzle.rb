# DAZZLE Homebrew Formula
#
# Installation: brew install manwithacat/tap/dazzle
# Or from this file: brew install ./homebrew/dazzle.rb

class Dazzle < Formula
  include Language::Python::Virtualenv

  desc "DSL-first application framework with LLM-assisted development"
  homepage "https://github.com/manwithacat/dazzle"
  url "https://github.com/manwithacat/dazzle/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "0570e36d34d274f824db3bfe91143d0695cc59528bac5c7df0daa23be2581e15"
  license "MIT"
  head "https://github.com/manwithacat/dazzle.git", branch: "main"

  depends_on "python@3.12"
  depends_on "rust" => :build  # Required for building pydantic-core

  # Core dependencies from pyproject.toml
  resource "pydantic" do
    url "https://files.pythonhosted.org/packages/source/p/pydantic/pydantic-2.9.2.tar.gz"
    sha256 "d155cef71265d1e9807ed1c32b4c8deec042a44a50a4188b25ac67ecd81a9c0f"
  end

  resource "pydantic-core" do
    url "https://files.pythonhosted.org/packages/source/p/pydantic-core/pydantic_core-2.23.4.tar.gz"
    sha256 "2584f7cf844ac4d970fba483a717dbe10c1c1c96a969bf65d61ffe94df1b2863"
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

  resource "shellingham" do
    url "https://files.pythonhosted.org/packages/source/s/shellingham/shellingham-1.5.4.tar.gz"
    sha256 "8dbca0739d487e5bd35ab3ca4b36e11c4078f3a234bfce294b0a0291363404de"
  end

  resource "rich" do
    url "https://files.pythonhosted.org/packages/source/r/rich/rich-13.9.2.tar.gz"
    sha256 "51a2c62057461aaf7152b4d611168f93a9fc73068f8ded2790f29fe2b5366d0c"
  end

  resource "markdown-it-py" do
    url "https://files.pythonhosted.org/packages/source/m/markdown-it-py/markdown-it-py-3.0.0.tar.gz"
    sha256 "e3f60a94fa066dc52ec76661e37c851cb232d92f9886b15cb560aaada2df8feb"
  end

  resource "mdurl" do
    url "https://files.pythonhosted.org/packages/source/m/mdurl/mdurl-0.1.2.tar.gz"
    sha256 "bb413d29f5eea38f31dd4754dd7377d4465116fb207585f97bf925588687c1ba"
  end

  resource "pygments" do
    url "https://files.pythonhosted.org/packages/source/p/pygments/pygments-2.18.0.tar.gz"
    sha256 "786ff802f32e91311bff3889f6e9a86e81505fe99f2735bb6d60ae0c5004f199"
  end

  def install
    virtualenv_install_with_resources
  end

  def caveats
    <<~EOS
      DAZZLE has been installed!

      Quick start:
        dazzle init my-project
        cd my-project
        dazzle build

      For LLM features, install optional dependencies:
        #{opt_libexec}/bin/pip install anthropic openai

      VS Code extension:
        code --install-extension dazzle.dazzle-dsl

      Set Python path in VS Code settings:
        "dazzle.pythonPath": "#{opt_libexec}/bin/python"

      Documentation:
        https://github.com/manwithacat/dazzle
    EOS
  end

  test do
    # Test that the CLI works
    assert_match "dazzle", shell_output("#{bin}/dazzle --help").downcase

    # Test basic functionality
    (testpath/"dazzle.toml").write <<~EOS
      [project]
      name = "test"
      module = "test"
      backend = "django_micro_modular"
    EOS

    (testpath/"dsl").mkpath
    (testpath/"dsl/app.dsl").write <<~EOS
      module test
      app test "Test App"

      entity Task "Task":
        id: uuid pk
        title: str(200) required
    EOS

    # Test validation
    system bin/"dazzle", "validate"
  end
end
