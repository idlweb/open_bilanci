from django.core.exceptions import ObjectDoesNotExist
import logging
from optparse import make_option
from django.conf import settings
from django.core.management import BaseCommand
from bilanci.models import Voce, ValoreBilancio
from bilanci.utils.comuni import FLMapper
from territori.models import Territorio, Contesto
from bilanci.utils import couch


class Command(BaseCommand):

    accepted_functions = ['contesto','cluster_mean','per_capita']

    option_list = BaseCommand.option_list + (
        make_option('--years',
                    dest='years',
                    default='',
                    help='Years to fetch. From 2002 to 2012. Use one of this formats: 2012 or 2003-2006 or 2002,2004,2006'),
        make_option('--cities',
                    dest='cities',
                    default='',
                    help="""
                        Cities codes or slugs. Use comma to separate values: Roma,Napoli,Torino or  "All".
                        NOTE: Cities are considered only for set_contesto function
                        """),
        make_option('--function','-f',
                    dest='function',
                    action='store',
                    default='',
                    help='Function to run: '+  ' | '.join(accepted_functions)),

        make_option('--couchdb-server',
                    dest='couchdb_server',
                    default=settings.COUCHDB_DEFAULT_SERVER,
                    help='CouchDB server to connect to (defaults to staging).'),

        make_option('--dry-run',
                    dest='dryrun',
                    action='store_true',
                    default=False,
                    help='Set the dry-run command mode: nothing is written in the db'),

    )

    help = """
        Compute additional necessary data for the Bilanci db: set Comuni context, mean value for Comuni clusters,
        per-capita Bilanci values and Political administration values
        """

    logger = logging.getLogger('management')
    comuni_dicts = {}


    def handle(self, *args, **options):
        verbosity = options['verbosity']
        if verbosity == '0':
            self.logger.setLevel(logging.ERROR)
        elif verbosity == '1':
            self.logger.setLevel(self.logger.wARNING)
        elif verbosity == '2':
            self.logger.setLevel(logging.INFO)
        elif verbosity == '3':
            self.logger.setLevel(logging.DEBUG)

        ###
        # function
        ###
        function = options['function']
        if not function:
            self.logger.error("Missing function parameter")
            return
        if function not in self.accepted_functions:
            self.logger.error("Function parameter value not accepted")
            return


        ###
        # dry run
        ###

        dryrun = options['dryrun']

        ###
        # cities
        ###

        cities_codes = options['cities']
        if not cities_codes and function != 'cluster_mean':
            self.logger.error("Missing city parameter")
            return

        self.logger.info("Opening Lista Comuni")
        mapper = FLMapper(settings.LISTA_COMUNI_PATH)
        cities = mapper.get_cities(cities_codes)
        if cities_codes.lower() != 'all':
            self.logger.info("Considering cities: {0}".format(cities))



        ###
        # years
        ###
        years = options['years']
        if not years:
            self.logger.error("Missing years parameter")
            return

        if "-" in years:
            (start_year, end_year) = years.split("-")
            years = range(int(start_year), int(end_year)+1)
        else:
            years = [int(y.strip()) for y in years.split(",") if 2001 < int(y.strip()) < 2013]

        if not years:
            self.logger.error("No suitable year found in {0}".format(years))
            return

        self.logger.info("Considering years: {0}".format(years))
        self.years = years


        ###
        # couchdb
        ###

        couchdb_server_alias = options['couchdb_server']
        couchdb_dbname = settings.COUCHDB_NORMALIZED_VOCI_NAME

        if couchdb_server_alias not in settings.COUCHDB_SERVERS:
            self.logger.error("Unknown couchdb server alias.")
            return


        self.logger.info("Connecting to db: {0}".format(couchdb_dbname))
        couchdb = couch.connect(
            couchdb_dbname,
            couchdb_server_settings=settings.COUCHDB_SERVERS[couchdb_server_alias]
        )


        if function == 'contesto':
            # set context in postgres db for Comuni
            self.set_contesto(couchdb, cities, years, dryrun)

        elif function == 'cluster_mean':
            # computes cluster mean for each value in the simplified tree
            cities_all = mapper.get_cities('all')
            self.set_cluster_mean(cities_all, years, dryrun)

        elif function == 'per_capita':
            # computes per-capita values
            self.set_per_capita(cities, years, dryrun)

        else:
            self.logger.error("Function not found, quitting")
            return



    def set_per_capita(self, cities, years, dryrun):
        for year in years:
            for city in cities:
                self.logger.info("Calculating per-capita value for Comune:{0} yr:{1}".\
                    format(city, year)
                )
                
                # looks for territorio in db
                try:
                    territorio = Territorio.objects.get(
                        territorio = 'C',
                        cod_finloc = city,
                    )
                except ObjectDoesNotExist:
                    self.logger.error("Territorio {0} does not exist in Territori db, quitting".format(city))
                    return

                # get context data for comune, anno
                try:
                    comune_context = Contesto.objects.get(
                        anno = year,
                        territorio = territorio,
                    )
                except ObjectDoesNotExist:
                    self.logger.error("Context could not be found for Comune:{0} year:{1}".\
                        format(territorio, year,)
                    )
                    continue

                n_abitanti = comune_context.popolazione_residente

                if n_abitanti > 0:
                    voci = ValoreBilancio.objects.filter(
                        anno = year,
                        territorio = territorio,
                    )
                    # for all the Voce in bilancio
                    # calculates the per_capita value

                    for voce in voci:
                        voce.valore_procapite = voce.valore / n_abitanti

                        # writes on db
                        if dryrun is False:
                            voce.save()

                else:
                    self.logger.warning("Inhabitants is ZERO for Comune:{0} year:{1}, can't calculate per-capita values".\
                        format(territorio, year,)
                        )



        return

    def set_cluster_mean(self, cities, years, dryrun):

        self.logger.info("Cluster mean start")

        for cluster in Territorio.CLUSTER:
            self.logger.info("Considering cluster: {0}".format(cluster[1]))
            # creates a fake territorio for each cluster if it doens't exist already
            territorio_cluster = Territorio.objects.\
                get_or_create(
                    denominazione = cluster[1],
                    territorio = Territorio.TERRITORIO.L,
                    cluster = cluster[0]
                )


            for year in years:
                self.logger.info("Considering year: {0}".format(year))
                for voce in Voce.objects.all():
                    self.logger.debug("Considering voce: {0}".format(voce))
                    totale = 0
                    n_cities = 0
                    for city in cities:
                        try:
                            territorio = Territorio.objects.get(
                                cod_finloc = city,
                            )
                        except ObjectDoesNotExist:
                            self.logger.error("Territorio:{0} doesnt exist, quitting".format(city))
                            return

                        try:
                            totale += ValoreBilancio.objects.get(
                                territorio = territorio,
                                anno = year,
                                voce = voce,
                            )
                            n_cities += 1
                        except ObjectDoesNotExist:
                            self.logger.warning("Voce: {0} doesnt exist for Comune: {1} year:{2} ".format(
                                voce, territorio, year
                            ))

                    if n_cities > 0:
                        media = totale / n_cities
                        valore_media = ValoreBilancio()
                        valore_media.voce = voce
                        valore_media.territorio = territorio_cluster
                        valore_media.anno = year
                        valore_media.valore = media
                        valore_media.save()




        return

    def set_contesto(self, couchdb, cities, years, dryrun):

        for city in cities:
            for year in years:
                self.logger.info(u"Setting Comune: {0}, year:{1}".format(city,year))

                bilancio_id = "{0}_{1}".format(year, city)
                # read data from couch
                if bilancio_id in couchdb:
                    bilancio_data = couchdb[bilancio_id]
                    if "01" in bilancio_data['consuntivo']:
                        if "quadro-1-dati-generali-al-31-dicembrenotizie-varie" in bilancio_data["consuntivo"]["01"]:
                            contesto_couch = bilancio_data["consuntivo"]["01"]\
                                ["quadro-1-dati-generali-al-31-dicembrenotizie-varie"]["data"]


                            # looks for territorio in db
                            try:
                                territorio = Territorio.objects.get(
                                    territorio = 'C',
                                    cod_finloc = city,
                                )
                            except ObjectDoesNotExist:
                                self.logger.error("Territorio {0} does not exist in Territori db, quitting".format(city))
                                return

                            # if the contesto data is not present, inserts the data in the db
                            # otherwise skips
                            try:
                                contesto_pg = Contesto.objects.get(
                                    anno = year,
                                    territorio = territorio,
                                )
                            except ObjectDoesNotExist:

                                # write data on postgres
                                if dryrun is False:
                                    contesto_dict = {}

                                    # contesto_keys maps the key in the couch doc and the name of
                                    # the field in the model

                                    contesto_keys = {
                                        "nuclei familiari (n)":"nuclei_familiari",
                                        "superficie urbana (ha)":"superficie_urbana",
                                        "superficie totale del comune (ha)":"superficie_totale",
                                        "popolazione residente (ab.)":"popolazione_residente",
                                        "lunghezza delle strade esterne (km)":"strade_esterne",
                                        "lunghezza delle strade interne centro abitato (km)":"strade_interne",
                                        "di cui: in territorio montano (km)":"strade_montane",
                                        }

                                    for contesto_key, contesto_value in contesto_keys.iteritems():
                                        if contesto_key in contesto_couch:
                                            contesto_dict[contesto_value] = clean_data(contesto_couch[contesto_key])

                                    contesto_dict['territorio'] = territorio
                                    contesto_dict['anno'] = year
                                    contesto_pg = Contesto(**contesto_dict)
                                    contesto_pg.save()



                        else:
                            self.logger.warning("Titolo 'quadro-1-dati-generali-al-31-dicembrenotizie-varie' not found for id:{0}, skipping". format(bilancio_id))
                    else:
                        self.logger.warning("Quadro '01' not found for id:{0}, skipping".format(bilancio_id))

                else:
                    self.logger.warning("Bilancio obj not found for id:{0}, skipping". format(bilancio_id))



def clean_data(data):
    c_data = data[0]
    if c_data:
        if c_data == "N.C.":
            return None
        else:
            # if the number contains a comma, it strips the decimal values
            if c_data.find(",") != -1:
                c_data = c_data[:c_data.find(",")]

            # removes the thousand-delimiter point and converts to int
            return int(c_data.replace(".",""))


