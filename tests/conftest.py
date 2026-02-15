"""Shared test fixtures and configuration."""

import os

# Set required env vars before anything imports config.settings
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")

import pytest

from src.scrapers.base_scraper import JobListing


# ---------------------------------------------------------------------------
# Indeed HTML fixtures
# ---------------------------------------------------------------------------

INDEED_CARD_FULL = """
<div class="job_seen_beacon">
  <h2 class="jobTitle">
    <a href="/rc/clk?jk=abc123" data-jk="abc123">
      <span>Senior Python Developer</span>
    </a>
  </h2>
  <span data-testid="company-name">Acme Corp</span>
  <div data-testid="text-location">New York, NY</div>
  <div class="salary-snippet-container">$120,000 - $150,000 a year</div>
  <div class="metadata">
    <div class="attribute_snippet">Full-time</div>
  </div>
  <div class="job-snippet">
    Build and maintain Python microservices for our platform.
  </div>
  <span class="date">Posted 3 days ago</span>
</div>
"""

INDEED_CARD_MINIMAL = """
<div class="job_seen_beacon">
  <h2 class="jobTitle">
    <a href="/viewjob?jk=def456">
      <span>Junior Data Analyst</span>
    </a>
  </h2>
  <span class="companyName">DataCo</span>
  <div class="companyLocation">Remote</div>
</div>
"""

INDEED_CARD_DATA_JK_FALLBACK = """
<div class="job_seen_beacon" data-jk="ghi789">
  <h2 class="jobTitle">
    <a data-jk="ghi789">
      <span>DevOps Engineer</span>
    </a>
  </h2>
  <span class="company">CloudInc</span>
  <span class="companyLocation">Austin, TX</span>
</div>
"""

INDEED_CARD_NO_TITLE_LINK = """
<div class="job_seen_beacon">
  <div class="companyName">NoCo</div>
</div>
"""

INDEED_CARD_EMPTY_TITLE = """
<div class="job_seen_beacon">
  <h2 class="jobTitle">
    <a href="/viewjob?jk=empty1">
      <span>   </span>
    </a>
  </h2>
</div>
"""

INDEED_CARD_ABSOLUTE_URL = """
<div class="job_seen_beacon">
  <h2 class="jobTitle">
    <a href="https://www.indeed.com/viewjob?jk=abs001">
      <span>Fullstack Engineer</span>
    </a>
  </h2>
  <span data-testid="company-name">WebCo</span>
  <div data-testid="text-location">San Francisco, CA</div>
</div>
"""

INDEED_CARD_SALARY_NO_MATCH = """
<div class="job_seen_beacon">
  <h2 class="jobTitle">
    <a href="/viewjob?jk=sal001">
      <span>Marketing Manager</span>
    </a>
  </h2>
  <span data-testid="company-name">MktCo</span>
  <div class="salary-snippet-container">Competitive benefits</div>
</div>
"""

INDEED_SEARCH_PAGE = """
<html><body>
<div class="jobsearch-ResultsList">
  <div class="job_seen_beacon">
    <h2 class="jobTitle">
      <a href="/rc/clk?jk=s001">
        <span>Backend Engineer</span>
      </a>
    </h2>
    <span data-testid="company-name">StartupX</span>
    <div data-testid="text-location">Remote</div>
    <div class="job-snippet">Work on distributed systems.</div>
  </div>
  <div class="job_seen_beacon">
    <h2 class="jobTitle">
      <a href="/rc/clk?jk=s002">
        <span>Frontend Engineer</span>
      </a>
    </h2>
    <span data-testid="company-name">StartupY</span>
    <div data-testid="text-location">Remote</div>
  </div>
</div>
</body></html>
"""

INDEED_SEARCH_PAGE_EMPTY = """
<html><body>
<div class="jobsearch-ResultsList"></div>
</body></html>
"""

INDEED_SEARCH_PAGE_DUPLICATE = """
<html><body>
<div class="jobsearch-ResultsList">
  <div class="job_seen_beacon">
    <h2 class="jobTitle">
      <a href="/rc/clk?jk=s001">
        <span>Backend Engineer</span>
      </a>
    </h2>
    <span data-testid="company-name">StartupX</span>
    <div data-testid="text-location">Remote</div>
  </div>
  <div class="job_seen_beacon">
    <h2 class="jobTitle">
      <a href="/rc/clk?jk=s001">
        <span>Backend Engineer</span>
      </a>
    </h2>
    <span data-testid="company-name">StartupX</span>
    <div data-testid="text-location">Remote</div>
  </div>
</div>
</body></html>
"""

INDEED_DETAIL_PAGE = """
<html><body>
  <h1 class="jobsearch-JobInfoHeader-title">Senior Python Developer</h1>
  <div data-testid="inlineHeader-companyName">
    <a>Acme Corp</a>
  </div>
  <div data-testid="inlineHeader-companyLocation">New York, NY</div>
  <div id="salaryInfoAndJobType">
    <span class="css-2iqe2o">$130,000 - $160,000 a year</span>
    <span>- Full-time</span>
  </div>
  <div id="jobDescriptionText">
    <p>We are looking for a Senior Python Developer.</p>
    <p>Requirements: 5+ years experience with Python.</p>
  </div>
</body></html>
"""

INDEED_DETAIL_PAGE_MINIMAL = """
<html><body>
  <h1>Some Job Title</h1>
</body></html>
"""

INDEED_DETAIL_PAGE_LOCATION_DASH = """
<html><body>
  <h1 class="jobsearch-JobInfoHeader-title">QA Tester</h1>
  <div data-testid="inlineHeader-companyLocation">- Seattle, WA</div>
  <div id="jobDescriptionText">Test things.</div>
</body></html>
"""

# ---------------------------------------------------------------------------
# Indeed alt-layout search page (data-jk variant)
# ---------------------------------------------------------------------------

INDEED_SEARCH_PAGE_ALT_LAYOUT = """
<html><body>
<div class="jobsearch-ResultsList">
  <div data-jk="alt001">
    <h2><a href="/viewjob?jk=alt001"><span>ML Engineer</span></a></h2>
    <span data-testid="company-name">AILabs</span>
    <div data-testid="text-location">Boston, MA</div>
  </div>
</div>
</body></html>
"""

# ---------------------------------------------------------------------------
# LinkedIn HTML used inside Playwright mocked pages
# ---------------------------------------------------------------------------

LINKEDIN_DETAIL_PAGE_FIELDS = {
    "title": "Staff Software Engineer",
    "company": "BigTech Inc",
    "location": "San Jose, CA",
    "description": "Lead a team of engineers building cloud infrastructure.",
    "salary": "$180,000 - $250,000/yr",
    "job_type": "full-time",
}
