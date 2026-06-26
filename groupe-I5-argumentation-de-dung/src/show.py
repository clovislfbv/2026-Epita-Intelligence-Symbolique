import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import networkx as nx


def show_graph(G, extension=set(), title=""):
    """
    Affiche le graphe orienté G.

    Vert  : argument dans l'extension
    Rouge : argument attaqué par l'extension
    Bleu  : argument ni dans l'extension ni attaqué par elle
    Contour noir : argument non attaqué (source)
    """

    plt.figure(figsize=(12, 9))
    plt.title(title, fontsize=14, fontweight="bold")

    set_ext = set(extension)

    # Couleurs des nœuds
    node_colors = []
    for node in G.nodes:
        if node in set_ext:
            node_colors.append("lightgreen")
        elif any(pred in set_ext for pred in G.predecessors(node)):
            node_colors.append("#ff6666")
        else:
            node_colors.append("skyblue")

    # Nœuds sources (sans attaquants)
    source_nodes = [n for n in G.nodes if G.in_degree(n) == 0]

    edgecolors = [
        "black" if node in source_nodes else "gray"
        for node in G.nodes
    ]

    linewidths = [
        2.5 if node in source_nodes else 1.0
        for node in G.nodes
    ]

    # Layout
    pos = nx.kamada_kawai_layout(G)

    ax = plt.gca()

    # Arêtes
    nx.draw_networkx_edges(
        G,
        pos,
        arrows=True,
        arrowsize=25,
        edge_color="gray",
        width=1.5,
        connectionstyle="arc3,rad=0.12",
        min_source_margin=15,
        min_target_margin=15,
    )

    # Met les flèches au-dessus des nœuds
    for patch in ax.patches:
        patch.set_zorder(3)

    # Nœuds
    nodes = nx.draw_networkx_nodes(
        G,
        pos,
        node_color=node_colors,
        node_size=1000,
        edgecolors=edgecolors,
        linewidths=linewidths,
    )
    nodes.set_zorder(2)

    # Labels
    labels = nx.draw_networkx_labels(
        G,
        pos,
        font_weight="bold"
    )

    for txt in labels.values():
        txt.set_zorder(4)

    # Légende
    vert_patch = mpatches.Patch(
        color="lightgreen",
        label="∈ E"
    )

    bleu_patch = mpatches.Patch(
        color="skyblue",
        label="∉ E"
    )

    rouge_patch = mpatches.Patch(
        color="#ff6666",
        label="attacked par E"
    )

    source_patch = mpatches.Circle(
        (0, 0),
        radius=0.1,
        facecolor="white",
        edgecolor="black",
        linewidth=2,
        label="source argument"
    )

    plt.legend(
        handles=[
            vert_patch,
            bleu_patch,
            rouge_patch,
            source_patch
        ],
        loc="upper left",
        title="Legend"
    )

    plt.axis("off")
    plt.tight_layout()
    plt.show()