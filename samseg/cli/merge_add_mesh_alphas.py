#!/usr/bin/env python

description = """Merge prior spatial probabilties (alphas) with those of an existing
SAMSEG mesh to create a new mesh/atlas. Should be run on the output of
gems_compute_atlas_probs.  

An example of use is the following:
fspython merge_add_mesh_alphas [...] --merge-labels 2 3 --add-indexes 3

Here we merge labels 2 and 3 and then add the third index of
estimated_alphas.npy to the mesh. For example, in case we used
gems_compute_alphas with --labels 2 3 99, we are adding label 99 to
the mesh. Indexes start from 1 since 0 is reserved for the background
class.

I also add a --merge-indexes flag in case the merge and add indexes
are mixed. If None the first indexes are used for merging. For
example: gems_compute_alphas --labels 2 99 3, I can do --merge-labels
2 3 --merge-indexes 1 3 --add-indexes 2.

Few things to consider:

- First merging and then add != first add and then merging. I
  implemented the former, but maybe it's better to implement both and
  leave the choice to the user. Not sure what the default should be
  though.

- How we add the extra class(es) can be done in different ways. For
  one class I did the following (same thing I did for MS lesion): add
  the new alphas and rescale everything else with (1-newalpha). For
  more than one class, the new alphas are just added and then the
  alphas are re-normalized. Again, maybe it's better to expose this to
  the user.

- You still need to manually modify the compressionLookupTable.txt
  file right now (i.e., adding extra entries at the end of the
  file). Might be worth considering doing this automatically in the
  script.

- Last functionality to add would be to remove some structures from
  the mesh, and automatically update the compressionLookupTable.txt
  file.

"""

import sys
import os
import numpy as np
import argparse
import surfa as sf
from samseg import gems

from samseg.io import kvlReadCompressionLookupTable


eps = np.finfo(float).eps

description = """
Merge/add prior spatial probabilities (alphas) with those of an existing
SAMSEG mesh to create a new mesh/atlas. Should be run on the output of
gems_compute_atlas_probs.
"""

def main():
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--out-dir', help='Output directory.', required=True)
    parser.add_argument('--estimated-alpha-dirs', nargs='+', help='Estimated alphas dirs', required=True)
    parser.add_argument('--samseg-atlas-dir', help='Samseg original directory; default in FS/average')
    parser.add_argument('--merge-labels', nargs='+', type=int, help='Labels to merge estimated alphas to.')
    parser.add_argument('--merge-indexes', nargs='+', type=int, help='Indexes of estimated alphas to merge to current alphas. First index is 1 (0 is background). If None, first indexes are used.')
    parser.add_argument('--merge-names', nargs='+', help='Structures name to merge estimated alphas to.')
    parser.add_argument('--add-indexes', nargs='+', type=int, help='Indexes of estimated alphas to add to current alphas. First index is 1 (0 is background).')
    parser.add_argument('--level', dest='levellist', type=int, nargs='+', help='Atlas level; default is 1 and 2')
    args = parser.parse_args()

    # Assuming 20 subjects were used to build the atlas
    samseg_subjects = 20

    # Get the samseg atlas dir
    if (args.samseg_atlas_dir != None):
        samseg_atlas_dir = args.samseg_atlas_dir
    else:
        fsh = os.environ.get('FREESURFER_HOME')
        samseg_atlas_dir = fsh + "/average/samseg/20Subjects_smoothing2_down2_smoothingForAffine2"

    if args.levellist != None:
        levellist = args.levellist
    else:
        levellist = [1, 2]

    # Make the output dir
    os.makedirs(args.out_dir, exist_ok=True)
    logfile = os.path.join(args.out_dir, 'merge_add_mesh_alphas.log')
    with open(logfile, "w") as f:
        f.write("cd " + os.getcwd() + "\n")
        f.write(' '.join(sys.argv) + "\n")
        f.write(samseg_atlas_dir + "\n")
    if args.merge_labels is not None:
        outlabelfile = os.path.join(args.out_dir, 'merged_labels.txt')
        with open(outlabelfile, "w") as f:
            for label in args.merge_labels:
                f.write(str(label) + "\n")

    for level in levellist:
        print("level = %d =========================================" % level)

        # Read in alphas
        estimated_alphas = []
        for adir in args.estimated_alpha_dirs:
            afile = os.path.join(adir, 'label_statistics_atlas_%d.npy' % level)
            a = np.load(afile)
            print("a " + str(a.shape))
            if (len(estimated_alphas) == 0):
                estimated_alphas = a
            else:
                estimated_alphas = np.concatenate((estimated_alphas, a), axis=2)
            # endif
        # endfor
        print(str(estimated_alphas.shape))

        # Retrieve all the SAMSEG related files
        # Here we are making some assumptions about file names
        mesh_collection_path = os.path.join(samseg_atlas_dir, "atlas_level" + str(level) + ".txt.gz")
        freesurfer_labels, names, colors = kvlReadCompressionLookupTable(
            os.path.join(samseg_atlas_dir, 'compressionLookupTable.txt'))
        # Get also compressed labels, as they are in the same order as FreeSurfer_labels
        compressed_labels = list(np.arange(0, len(freesurfer_labels)))

        # Read mesh collection
        print("Loading mesh collection at: " + str(mesh_collection_path))
        mesh_collection = gems.KvlMeshCollection()
        mesh_collection.read(mesh_collection_path)

        # Load reference mesh
        mesh = mesh_collection.reference_mesh
        alphas = mesh.alphas.copy()

        # First merge classes
        if args.merge_labels is not None:
            for l, merge_label in enumerate(args.merge_labels):
                if args.merge_indexes is not None:
                    idx2 = args.merge_indexes[l]
                else:
                    idx2 = l + 1
                idx = freesurfer_labels.index(merge_label)
                alphas[:, idx] = (alphas[:, idx] * samseg_subjects + np.sum(estimated_alphas[:, idx2, :], axis=1)) \
                             / (samseg_subjects + estimated_alphas.shape[2])
        if args.merge_names is not None:
            for merge_name in args.merge_names:
                if args.merge_indexes is not None:
                    idx2 = args.merge_indexes[l]
                else:
                    idx2 = l + 1
                idx = names.index(merge_name)
                alphas[:, idx] = (alphas[:, idx] * samseg_subjects + np.sum(estimated_alphas[:, idx2, :], axis=1)) \
                                  / (samseg_subjects + estimated_alphas.shape[2])
            # for mergnames
        # endif

        # Re-normalize alphas
        if args.merge_labels is not None or args.merge_names is not None:
            normalizer = np.sum(alphas, axis=1) + eps
            alphas = alphas / normalizer[:, None]

        # Here we add classes. This is done after merging classes (if any).
        # Note that switching the order of merging and adding produces a different output
        if args.add_indexes is not None:
            tmp = np.zeros([alphas.shape[0], alphas.shape[1] + len(args.add_indexes)])
            tmp[:, :alphas.shape[1]] = alphas.copy()
            if len(args.add_indexes) == 1:
                idx = args.add_indexes[0]
                # Only one class to add (every other class is lower down by a factor (1-estimated-alpha)
                tmp[:, -1] = np.mean(estimated_alphas[:, idx, :], axis=1)
                tmp[:, :alphas.shape[1]] *= (1 - tmp[:, -1])[:, None]
            else:
                # More than one class, add all the estimated alphas and re-normalize
                for l, idx in enumerate(args.add_indexes):
                    tmp[:, alphas.shape[1] + l] = np.mean(estimated_alphas[:, idx, :], axis=1)
                normalizer = np.sum(tmp, axis=1) + eps
                tmp = tmp / normalizer[:, None]

            alphas = tmp

        # Add alphas in mesh
        mesh.alphas = alphas
        # Save mesh
        mesh_collection.write(os.path.join(args.out_dir, "atlas_level" + str(level) + ".txt"))
    # end loop over levels

    print("merge_add_mesh_alphas done")


if __name__ == '__main__':
    main()
