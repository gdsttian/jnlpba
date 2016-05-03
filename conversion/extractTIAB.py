#!/usr/bin/env python

from __future__ import with_statement

import sys
import re
import os
import gzip

try:
    import xml.etree.ElementTree as ET
except ImportError: 
    import cElementTree as ET   

options = None
output_count, skipped_count = 0,0

def argparser():
    import argparse

    ap=argparse.ArgumentParser(description='Extract per-document title ' +
                               'and abstract texts from PubMed XML.')
    ap.add_argument('-o', '--output-dir', metavar='DIR', default=None, 
                    help='base output directory (output to STDOUT if none)')
    ap.add_argument('-gt', '--PMID-greater-than', metavar='PMID', default=None,
                    help='only process PMIDs greater than given value.')
    ap.add_argument('-lt', '--PMID-lower-than', metavar='PMID', default=None,
                    help='only process PMIDs lower than given value.')
    ap.add_argument('-sa', '--single-line-abstract', default=False, 
                    action='store_true', 
                    help='always output abstract on single line.')
    ap.add_argument('-v', '--verbose', default=False, action='store_true',
                    help='verbose output.')
    ap.add_argument('files', metavar='FILE', nargs='+', 
                    help='input PubMed XML file(s).')
    return ap

def process(fn):
    global options, output_count, skipped_count

    # create a directory for this package if specified
    if options.output_dir:
        outputDir = os.path.join(options.output_dir, filenamebase)
        # TODO: fail gracefully on problems
        os.mkdir(outputDir)
    else:
        outputDir = None
    
    # if the extension suggests a zip, wrap
    input = fn
    gzipped = False
    if re.search('\.gz$', fn):
        input = gzip.GzipFile(fn)
        gzipped = True

    for event, element in ET.iterparse(input):
        # we're only interested in tracking citation end events
        if event != "end" or element.tag != "MedlineCitation":
            continue

        citation = element

        # the citation element should have exactly one PMID child
        PMIDs = citation.findall("PMID")
        assert len(PMIDs) == 1, "ERROR: expected 1 PMID, got %d" % len(PMIDs)
        PMID = PMIDs[0]

        # if a PMID range has been specified, check that we're in the
        # range
        if ((options.PMID_greater_than is not None and 
             int(PMID.text) <= options.PMID_greater_than) or
            (options.PMID_lower_than is not None and
             int(PMID.text) >= options.PMID_lower_than)):
            if options.verbose:
                print >> sys.stderr, "Note: skipping %s",
                if options.PMID_greater_than is not None:
                     print >> sys.stderr, "(lower limit %d)" % (PMID.text, options.PMID_greater_than),
                if options.PMID_lower_than is not None:
                     print >> sys.stderr, "(upper limit %d)" % (PMID.text, options.PMID_lower_than),
                print >> sys.stderr
            skipped_count += 1
            # clear out the element; we're not going to use it.
            citation.clear()
            continue

        # likewise, there should be exactly one Article child
        articles = citation.findall("Article")
        assert len(articles) == 1, "ERROR: %d articles for PMID %s" % (len(articles), PMID.text)
        article = articles[0]

        # further, Article should have a single ArticleTitle
        articleTitles = article.findall("ArticleTitle")
        assert len(articleTitles) == 1, "ERROR: %d titles for PMID %s" % (len(articleTitles, PMID.text))
        articleTitle = articleTitles[0]

        # also, Article typically (but not always) contains an Abstract
        abstracts = article.findall("Abstract")
        assert len(abstracts) in (0,1), "ERROR: %d abstracts for PMID %s" % (len(abstracts, PMID.text))
        abstract = None
        if abstracts != []:
            abstract = abstracts[0]

        # if there's no Abstract, try to look for <OtherAbstract> in
        # the citation (not the article) element, which seems to be
        # used in some cases
        if abstract is None:
            otherAbstracts = citation.findall("OtherAbstract")
            # This happens a few times.
            if len(otherAbstracts) > 1 and options.verbose:
                print >> sys.stderr, "NOTE: %d 'other' abstracts for PMID %s. Only printing first." % (len(otherAbstracts), PMID.text)
            if otherAbstracts != []:
                abstract = otherAbstracts[0]

        abstractText = None
        textAbstract = ""
        if abstract is not None:
            # if there's an Abstract, it should contain an AbstractText
            abstractTexts = abstract.findall("AbstractText")
            assert len(abstractTexts) != 0, "ERROR: %d abstract texts for PMID %s" % (len(abstractTexts), PMID.text)

            if len(abstractTexts) == 1:
                abstractText = abstractTexts[0]
                textAbstract = abstractText.text
            else:
                # recent versions of PubMed data may contain multiple
                # AbstractText elements for structured abstracts. In these
                # cases, "label" attributes give structured abstract
                # section headers and should be combined into the text.
                assert len(abstractTexts) > 1, "INTERNAL ERROR"
                if options.verbose:
                    print >> sys.stderr, "NOTE: multiple <AbstractText>s for %s" % PMID.text
                sectionTexts = []

                for at in abstractTexts:
                    # there may be instances of empty <AbstractText>
                    # elements in the data (see e.g. PMID 20619000 in
                    # the PubMed 2012 baseline). Skip those with the
                    # special "empty" label "UNLABELLED" entirely;
                    # print the label only for the rest.
                    if ((at.text is None or at.text.strip() == "") and 
                        at.attrib.get("Label","") == "UNLABELLED"):
                        if options.verbose:
                            print >> sys.stderr, "NOTE: skipping empty <AbstractText>s with label \"UNLABELLED\" in %s" % PMID.text
                        continue

                    t = ""
                    if "Label" in at.attrib:
                        if at.attrib["Label"] != "UNLABELLED":
                            t = at.attrib["Label"] + ":"
                    else:
                        print >> sys.stderr, "Warning: missing 'Label' for multiple <AbstractText>s in %s" % PMID.text

                    if at.text is None or at.text.strip() == "":
                        print >> sys.stderr, "NOTE: empty text for one of multiple <AbstractText>s in %s" % PMID.text
                    else:
                        if t and not t.isspace():
                            if options.single_line_abstract:
                                t += " "
                            else:
                                t += "\n"
                        t += at.text
                    sectionTexts.append(t)

                if options.single_line_abstract:                
                    textAbstract = " ".join(sectionTexts)
                else:
                    textAbstract = "\n".join(sectionTexts)

        # OK, we've got all we need. Now we just need the texts
        textPMID     = PMID.text
        textTitle    = articleTitle.text        

        # bit of sanity checking
        assert re.match(r'^\d+$', textPMID), "ERROR: unexpected characters in PMID: '%s'" % textPMID

        # output
        if outputDir is None:
            out = sys.stdout
        else:
            outputFile = os.path.join(outputDir, textPMID + ".txt")
            out = open(outputFile, "w")

        print >> out, textTitle.encode("UTF-8")
        if textAbstract:
            print >> out, textAbstract.encode("UTF-8")
        elif options.verbose:
            print >> sys.stderr, "No abstract for %s" % textPMID

        if outputDir is not None:
            out.close()

        output_count += 1
        
        # finally, clear out the used data; we don't need it anymore.
        citation.clear()

    # if we were wrapping a .gz, close the GzipFile
    if gzipped:
        input.close()

def main(argv=None):
    global options, output_count, skipped_count

    if argv is None:
        argv = sys.argv

    options = argparser().parse_args(argv[1:])

    if options.PMID_greater_than is not None:
        options.PMID_greater_than = int(options.PMID_greater_than)
    if options.PMID_lower_than is not None:
        options.PMID_lower_than = int(options.PMID_lower_than)

    for fn in options.files:
        process(fn)

    if options.verbose:
        print >> sys.stderr, "Done. Output texts for %d PMIDs, skipped %d." % (output_count, skipped_count)

if __name__ == "__main__":
    sys.exit(main(sys.argv))
