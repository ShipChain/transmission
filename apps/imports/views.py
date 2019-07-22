from django.shortcuts import render




# class CsvDocumentViewSet(mixins.CreateModelMixin,
#                          mixins.RetrieveModelMixin,
#                          mixins.UpdateModelMixin,
#                          mixins.ListModelMixin,
#                          viewsets.GenericViewSet):
#     queryset = CsvDocument.objects.all()
#     serializer_class = CsvDocumentSerializer
#     permission_classes = (permissions.IsAuthenticated, UserHasCsvFilePermission, )
#     filter_backends = (filters.DjangoFilterBackend, )
#     filter_class = CsvDocumentFilterSet
#
#     def get_queryset(self):
#         return self.queryset.filter(updated_by=self.request.user.id)
#
#     def perform_create(self, serializer):
#         if settings.PROFILES_ENABLED:
#             created = serializer.save(owner_id=get_owner_id(self.request), updated_by=self.request.user.id)
#         else:
#             created = serializer.save()
#         return created
#
#     def perform_update(self, serializer):
#         if settings.PROFILES_ENABLED:
#             updated = serializer.save(updated_by=self.request.user.id)
#         else:
#             updated = serializer.save()
#         return updated
#
#     def create(self, request, *args, **kwargs):
#         """
#         Create a pre-signed s3 post and create a corresponding document object with pending status
#         """
#         LOG.debug(f'Creating a CSV document object.')
#         log_metric('transmission.info', tags={'method': 'documents.create', 'module': __name__})
#
#         serializer = CsvDocumentCreateSerializer(data=request.data, context={'auth': get_jwt_from_request(request)})
#         serializer.is_valid(raise_exception=True)
#         doc_obj = self.perform_create(serializer)
#
#         return Response(CsvDocumentCreateResponseSerializer(doc_obj).data, status=status.HTTP_201_CREATED)
