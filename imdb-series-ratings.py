import argparse
import sys
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt


def error(*args, **kwargs):
    print("[ERROR]", *args, **kwargs, file=sys.stderr)


def info(*args, **kwargs):
    print("[INFO]", *args, **kwargs)

def load_basics(usecols):
    info("Loading title.basics.tsv")
    return pd.read_csv(
        "title.basics.tsv",
        sep="\t",
        dtype={
            "tconst": "object",
            "titleType": "object",
            "primaryTitle": "object",
            "originalTitle": "object",
            "isAdult": "object",
            "startYear": "Int64",
            "endYear": "Int64",
            "runtimeMinutes": "Int64",
            "genres": str,
        },
        na_values={"\\N"},
        index_col=0,
        usecols=usecols,
    )


def main(args):
    title = None

    if args.name is not None:
        basics = load_basics(usecols=[0, 1, 2, 5, 6])

        matched = basics[
            (basics["primaryTitle"] == args.name) & (basics["titleType"] == "tvSeries")
        ]

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

        chosen = matched.index[chosen]
        title  = matched.at[chosen, 'primaryTitle']
    elif args.id is not None:
        chosen = args.id
    else:
        error("Expected either --id or --name")
        exit(2)

    if title is None:
        title = load_basics(usecols=[0, 2]).at[chosen, 'primaryTitle']

    info("Loading episode titles")
    episode = pd.read_csv(
        "title.episode.tsv",
        sep="\t",
        dtype={
            "tconst": str,
            "parentTconst": str,
            "seasonNumber": "Int64",
            "episodeNumber": "Int64",
        },
        na_values={"\\N"},
        index_col=0,
    )

    info("Loading ratings")
    ratings = pd.read_csv("title.ratings.tsv", sep="\t", dtype={
        "tconst": "string",
        "averageRating": "Float32",
        "numVotes": "Int64"
    }, index_col=0)

    episodes_rated = episode[episode["parentTconst"] == chosen].join(ratings)

    plt.title(title)

    if args.box:
        sns.boxplot(x='seasonNumber', y='averageRating', data=episodes_rated)
        plt.xlabel("Season number")
        plt.ylabel("Average episode rating")
        plt.show()
    elif args.episodes:
        sns.lineplot(x='episodeNumber', y='averageRating', data=episodes_rated)
        plt.xlabel("Episode number")
        plt.ylabel("Average episode rating")
        plt.show()
    else:
        error("Expected one of graph generation options")
        exit(2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Plots and statistics about TV series ratings using IMDb database"
    )

    parser.add_argument("-i", "--id", help="ID of the series")
    parser.add_argument("-n", "--name", help="Name of the series")

    parser.add_argument("--box", help="Generate box plot", action="store_true")
    parser.add_argument("--episodes", help="Generate line plot", action="store_true")

    args = parser.parse_args()

    if args.name is None and args.id is None:
        error("Either name or id of the show was expected")
        parser.print_usage(sys.stderr)
        exit(2)

    main(args)
