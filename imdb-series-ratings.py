# TODO: Add by episode breakdown for completion mode
# TODO: runtime estimation doesn't work for last season of Doom Patrol, don't report it when there are NA's
import argparse
import csv
import gzip
import itertools
import matplotlib.pyplot as plt
import os
import seaborn as sns
import pandas as pd
import shutil
import sys
import urllib.request
import duckdb

verbosity_level = 0

TABLES = (
    ("title.basics.tsv", "basics"),
    ("title.episode.tsv", "episode"),
    ("title.ratings.tsv", "ratings"),
)

def error(*args, **kwargs):
    print("[ERROR]", *args, **kwargs, file=sys.stderr, flush=True)


def info(*args, **kwargs):
    if verbosity_level > 0:
        print("[INFO]", *args, **kwargs, flush=True)

def download_dataset():
    for tsv, _ in TABLES:
        gz = f"{tsv}.gz"
        if not os.path.exists(gz):
            info(f"Downloading {gz}")
            urllib.request.urlretrieve(f"https://datasets.imdbws.com/{gz}", gz)

        if not os.path.exists(tsv):
            info(f"Decompressing {tsv} from {gz}")
            with gzip.open(gz, "rb") as f_in, open(tsv, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)


def load_tables():
    for file, table in TABLES:
        duckdb.sql(
            r"""
            CREATE TABLE {table} AS
            SELECT *
            FROM read_csv('{file}', delim = '\t', header=true, quote=NULL, nullstr='\N')
        """.format(
                table=table, file=file
            )
        )


def resolve_imdb_id_and_title(args) -> tuple[str, str]:
    # TODO: This is a code smell, the caller should decide what they want
    title_required = args.mode in ("box", "episodes")

    if args.name is not None:
        duckdb.execute(
            r"""
            SELECT tconst, primaryTitle, startYear, endYear
            FROM basics
            WHERE primaryTitle == ? AND titleType == 'tvSeries'
        """,
            [args.name],
        )
        matched = duckdb.fetchall()

        info(f"Matched {len(matched)} title" + ("" if len(matched) == 0 else "s"))
        chosen = 0 if len(matched) == 1 else None

        while chosen is None:
            print("Matched multiple titles. Choose one that you meant:")
            for n, (index, row) in enumerate(matched.iterrows()):
                _, primaryTitle, startYear, endYear = row
                print(f"({n+1})", index, primaryTitle, startYear, endYear)
            print(end="", flush=True)
            chosen_ = input("Choose: ")
            if 1 <= (chosen_ := int(chosen_)) <= len(matched):
                chosen = chosen_ - 1
                break

        return matched[chosen][:2]
    elif args.id is not None:
        if title_required:
            duckdb.execute(
                "SELECT tconst, primaryTitle FROM basics WHERE tconst = ?", [args.id]
            )
            return duckdb.fetchone()
        else:
            return (args.id, None)
    else:
        error("Expected either --id or --name")
        exit(2)


def hours_minutes(minutes: int) -> str:
    assert minutes >= 0, "pre: minutes must be >= 0"

    hours = minutes // 60
    minutes %= 60
    hours = [f"{hours}h"] if hours > 0 else []
    minutes = [f"{minutes}min"] if minutes > 0 else []
    return f" ({result})" if (result := " ".join([*hours, *minutes])) else ""


def collapse_years(years: list[int]) -> str:
    assert all(a <= b for a, b in zip(years, years[1:])), "pre: years must be sorted"

    def do():
        start = years[0]
        previous = years[0]
        for year in itertools.chain(years[1:], (None,)):
            if year == previous + 1:
                previous = year
                continue
            if start == previous:
                yield f"{start}"
            else:
                yield f"{start}-{previous}"
            start = year
            previous = year

    return ", ".join(do())


def main(args):
    download_dataset()
    load_tables()

    tconst, title = resolve_imdb_id_and_title(args)

    if args.mode == "box":
        duckdb.execute(
            """
            SELECT seasonNumber, averageRating
            FROM episode e
            INNER JOIN ratings r ON e.tconst = r.tconst
            WHERE parentTconst = ?
        """,
            [tconst],
        )
        episodes_rated = duckdb.fetch_df()
        plt.title(title)
        sns.boxplot(x="seasonNumber", y="averageRating", data=episodes_rated)
        plt.xlabel("Season number")
        plt.ylabel("Average episode rating")
        plt.show()
    elif args.mode == "episodes":
        duckdb.execute(
            """
            SELECT episodeNumber, averageRating
            FROM episode e
            INNER JOIN ratings r ON e.tconst = r.tconst
            WHERE parentTconst = ?
        """,
            [tconst],
        )
        episodes_rated = duckdb.fetch_df()
        plt.title(title)
        sns.lineplot(x="episodeNumber", y="averageRating", data=episodes_rated)
        plt.xlabel("Episode number")
        plt.ylabel("Average episode rating")
        plt.show()
    elif args.mode == "completion":
        duckdb.execute(
            """
            SELECT b.tconst as tconst, seasonNumber, episodeNumber, runtimeMinutes, startYear
            FROM basics b INNER JOIN episode e ON b.tconst = e.tconst
            WHERE parentTconst = ?
        """,
            [tconst],
        )
        episodes = duckdb.fetch_df()

        episodes_in_season = episodes[
            (episodes["seasonNumber"] == args.season)
            & (episodes["episodeNumber"] >= args.episode)
        ]
        next_seasons = episodes[episodes.fillna(0)["seasonNumber"] > args.season]
        episodes_left = pd.concat([episodes_in_season, next_seasons])

        episodes_left_count = episodes_left["episodeNumber"].shape[0]
        episodes_count = episodes.shape[0]

        total_runtime = episodes["runtimeMinutes"].sum()
        remaining_runtime = episodes_left["runtimeMinutes"].sum()

        years = sorted(episodes["startYear"].dropna().unique())

        print(
            f"Completed {episodes_count - episodes_left_count} episodes"
            f" with {episodes_left_count} left"
            f" from {episodes_count} episodes total"
            f" ({100-episodes_left_count/episodes_count*100:.2f}%)"
        )
        print(
            f"Watched {total_runtime - remaining_runtime} minutes{hours_minutes(total_runtime - remaining_runtime)}"
            f" with {remaining_runtime} minutes left{hours_minutes(remaining_runtime)}"
            f" from {total_runtime} minutes total{hours_minutes(total_runtime - remaining_runtime)}"
            f" ({100-remaining_runtime/total_runtime*100:.2f}%)"
        )
        print(f"Series episodes were released in {collapse_years(years)}")
        print()
        for season in sorted(episodes_left["seasonNumber"].unique()):
            remaining_episodes_in_season = episodes_left[
                episodes_left["seasonNumber"] == season
            ]
            remaining_episodes_in_season_runtime = remaining_episodes_in_season[
                "runtimeMinutes"
            ].sum()
            span = collapse_years(
                sorted(remaining_episodes_in_season["startYear"].dropna().unique())
            )
            print(
                f"- In season {season} ({span}) there are {remaining_episodes_in_season.shape[0]} remaining episodes"
                f" with total runtime of {remaining_episodes_in_season_runtime} minutes{hours_minutes(remaining_episodes_in_season_runtime)}"
                f" ({remaining_episodes_in_season_runtime/total_runtime*100:.2f}% of whole series)"
            )
    else:
        error(f"Unknown mode: {args.mode}")
        exit(2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Plots and statistics about TV series ratings using IMDb database"
    )
    parser.add_argument("-i", "--id", help="ID of the series")
    parser.add_argument("-n", "--name", help="Name of the series")
    parser.add_argument("-v", "--verbose", action="count", default=0)

    subparsers = parser.add_subparsers(required=True)

    episodes = subparsers.add_parser("episodes", help="Generate line plot")
    episodes.set_defaults(mode="episodes")

    box = subparsers.add_parser("box", help="Generate box plot")
    box.set_defaults(mode="box")

    completion = subparsers.add_parser(
        "completion", help="Calculate how much of given series was completed"
    )
    completion.set_defaults(mode="completion")
    completion.add_argument(
        "-s", "--season", help="Current season of given series", required=True, type=int
    )
    completion.add_argument(
        "-e",
        "--episode",
        help="Current episode of given series",
        required=True,
        type=int,
    )

    args = parser.parse_args()
    verbosity_level = args.verbose
    main(args)
