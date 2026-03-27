"""Tests for structural HTML assertions."""

from dazzle.testing.ux.structural import (
    check_detail_view,
    check_form,
    check_html,
)


class TestCheckDetailView:
    def test_valid_detail_passes(self) -> None:
        html = """
        <div data-dazzle-entity="Task">
          <a href="/app/task" class="btn">Back</a>
          <h2>Task Detail</h2>
        </div>
        """
        results = check_detail_view(html)
        assert all(r.passed for r in results)

    def test_missing_back_button_fails(self) -> None:
        html = """
        <div data-dazzle-entity="Task">
          <h2>Task Detail</h2>
        </div>
        """
        results = check_detail_view(html)
        back_check = next((r for r in results if "back" in r.check_name.lower()), None)
        assert back_check is not None
        assert not back_check.passed


class TestCheckForm:
    def test_valid_form_passes(self) -> None:
        html = """
        <form action="/api/task" method="post">
          <input name="title" required aria-required="true">
          <button type="submit">Save</button>
        </form>
        """
        results = check_form(html)
        assert all(r.passed for r in results)

    def test_missing_submit_button_fails(self) -> None:
        html = """
        <form action="/api/task" method="post">
          <input name="title" required>
        </form>
        """
        results = check_form(html)
        submit_check = next((r for r in results if "submit" in r.check_name.lower()), None)
        assert submit_check is not None
        assert not submit_check.passed

    def test_empty_action_fails(self) -> None:
        html = """
        <form action="" method="post">
          <button type="submit">Save</button>
        </form>
        """
        results = check_form(html)
        action_check = next((r for r in results if "action" in r.check_name.lower()), None)
        assert action_check is not None
        assert not action_check.passed


class TestCheckHtml:
    def test_duplicate_ids_detected(self) -> None:
        html = """
        <div id="foo">A</div>
        <div id="foo">B</div>
        """
        results = check_html(html)
        dup_check = next((r for r in results if "duplicate" in r.check_name.lower()), None)
        assert dup_check is not None
        assert not dup_check.passed

    def test_img_without_alt_detected(self) -> None:
        html = '<img src="/photo.jpg">'
        results = check_html(html)
        alt_check = next((r for r in results if "alt" in r.check_name.lower()), None)
        assert alt_check is not None
        assert not alt_check.passed

    def test_clean_html_passes(self) -> None:
        html = """
        <div id="a">
          <img src="/photo.jpg" alt="Photo">
        </div>
        """
        results = check_html(html)
        assert all(r.passed for r in results)
